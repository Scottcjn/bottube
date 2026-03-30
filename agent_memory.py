# SPDX-License-Identifier: MIT
"""
Agent Memory Layer — Self-Referencing Past Content

Gives BoTTube agents memory of their own videos, enabling natural
self-references like "Following up on my video about X..." or
"I changed my mind since my last take on this."

Features:
- TF-IDF vector store per agent (no external deps)
- Topic tracking, opinion logging, series detection
- Milestone awareness ("This is my 100th video!")
- Self-reference suggestion engine

Usage:
    mem = AgentMemory(agent="cosmo_bot", db_path="memory.db")
    mem.ingest_video(video_id="v1", title="Why PowerPC Rules", description="...", tags=["hardware"])
    ref = mem.suggest_reference("PowerPC architecture today")
    # SelfReference(type="followup", text="Following up on my video 'Why PowerPC Rules'...")

API:
    GET /api/v1/agents/{name}/memory?query=topic
    GET /api/v1/agents/{name}/stats

Closes Scottcjn/rustchain-bounties#2285
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# TF-IDF Vector Store (zero external dependencies)
# ---------------------------------------------------------------------------

class TfIdfStore:
    """Simple TF-IDF similarity search. No numpy/sklearn needed."""

    def __init__(self):
        self._docs: Dict[str, List[str]] = {}  # doc_id -> tokens
        self._idf: Dict[str, float] = {}
        self._dirty = True

    def add(self, doc_id: str, text: str):
        tokens = self._tokenize(text)
        self._docs[doc_id] = tokens
        self._dirty = True

    def remove(self, doc_id: str):
        self._docs.pop(doc_id, None)
        self._dirty = True

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """Return top_k (doc_id, score) pairs sorted by cosine similarity."""
        if self._dirty:
            self._rebuild_idf()
        query_tokens = self._tokenize(query)
        query_vec = self._tfidf_vec(query_tokens)
        if not query_vec:
            return []

        results = []
        for doc_id, doc_tokens in self._docs.items():
            doc_vec = self._tfidf_vec(doc_tokens)
            score = self._cosine(query_vec, doc_vec)
            if score > 0.01:
                results.append((doc_id, score))

        results.sort(key=lambda x: -x[1])
        return results[:top_k]

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return [w for w in text.split() if len(w) > 2]

    def _rebuild_idf(self):
        n = len(self._docs)
        if n == 0:
            self._idf = {}
            self._dirty = False
            return
        df: Counter = Counter()
        for tokens in self._docs.values():
            unique = set(tokens)
            for t in unique:
                df[t] += 1
        # Use smoothed IDF: log((n+1) / (count+1)) + 1 to handle single-doc case
        self._idf = {t: math.log((n + 1) / (count + 1)) + 1.0 for t, count in df.items()}
        self._dirty = False

    def _tfidf_vec(self, tokens: List[str]) -> Dict[str, float]:
        tf: Counter = Counter(tokens)
        total = len(tokens) or 1
        vec = {}
        for t, count in tf.items():
            idf = self._idf.get(t, 0)
            vec[t] = (count / total) * idf
        return vec

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        keys = set(a) & set(b)
        if not keys:
            return 0.0
        dot = sum(a[k] * b[k] for k in keys)
        mag_a = math.sqrt(sum(v * v for v in a.values()))
        mag_b = math.sqrt(sum(v * v for v in b.values()))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ReferenceType(str, Enum):
    FOLLOWUP = "followup"
    CHANGED_MIND = "changed_mind"
    CALLBACK = "callback"
    SERIES = "series"
    MILESTONE = "milestone"
    FIRST_TIME = "first_time"


@dataclass
class SelfReference:
    """A suggested self-reference for a new video."""
    type: ReferenceType
    text: str
    related_video_id: Optional[str] = None
    related_title: Optional[str] = None
    confidence: float = 0.0


@dataclass
class VideoRecord:
    """Stored record of an agent's video."""
    video_id: str
    title: str
    description: str
    tags: List[str]
    opinions: List[str]
    created_at: float


@dataclass
class AgentStats:
    """Agent statistics."""
    total_videos: int
    first_upload: Optional[float]
    top_topics: List[Tuple[str, int]]
    days_active: int
    current_series: List[str]


# ---------------------------------------------------------------------------
# Memory Engine
# ---------------------------------------------------------------------------

class AgentMemory:
    """
    Memory layer for a BoTTube agent.

    Parameters
    ----------
    agent : str
        Agent name/identifier.
    db_path : str | Path | None
        SQLite path. None = in-memory.
    now_fn : callable | None
        Override for time.time().
    """

    def __init__(
        self,
        agent: str = "default",
        db_path: str | Path | None = None,
        now_fn=None,
    ):
        self.agent = agent
        self._now_fn = now_fn or time.time
        self._db_path = str(db_path) if db_path else ":memory:"
        self._init_db()
        self._store = TfIdfStore()
        self._load_into_store()

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    def ingest_video(
        self,
        video_id: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        opinions: Optional[List[str]] = None,
    ):
        """Add a video to the agent's memory."""
        now = self._now_fn()
        tags = tags or []
        opinions = opinions or []

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agent_videos "
                "(agent, video_id, title, description, tags, opinions, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    self.agent, video_id, title, description,
                    json.dumps(tags), json.dumps(opinions), now,
                ),
            )

        # Update TF-IDF store
        text = f"{title} {description} {' '.join(tags)}"
        self._store.add(video_id, text)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> List[Tuple[VideoRecord, float]]:
        """Search agent's memory by semantic similarity."""
        results = self._store.search(query, top_k=top_k)
        output = []
        for vid_id, score in results:
            record = self._get_video(vid_id)
            if record:
                output.append((record, score))
        return output

    def has_covered_topic(self, topic: str, threshold: float = 0.15) -> bool:
        """Check if agent has previously covered a topic."""
        results = self._store.search(topic, top_k=1)
        return bool(results and results[0][1] >= threshold)

    def suggest_reference(
        self,
        new_title: str,
        new_description: str = "",
        threshold: float = 0.1,
    ) -> Optional[SelfReference]:
        """
        Suggest a self-reference for a new video being created.

        Returns the best reference, or None if no relevant past content.
        """
        stats = self.get_stats()

        # Milestone check first
        milestone_ref = self._check_milestone(stats)
        if milestone_ref:
            return milestone_ref

        # Series detection
        series_ref = self._check_series(new_title, stats)
        if series_ref:
            return series_ref

        # Semantic search for related content
        query = f"{new_title} {new_description}"
        results = self.search(query, top_k=3)

        if not results:
            return SelfReference(
                type=ReferenceType.FIRST_TIME,
                text="First time covering this topic",
                confidence=0.8,
            )

        best_video, best_score = results[0]

        if best_score < threshold:
            return SelfReference(
                type=ReferenceType.FIRST_TIME,
                text="First time covering this topic",
                confidence=0.6,
            )

        # Check if opinions might have changed
        if best_video.opinions:
            return SelfReference(
                type=ReferenceType.CHANGED_MIND,
                text=(
                    f"I changed my mind since my last take on this — "
                    f"in '{best_video.title}' I said "
                    f"'{best_video.opinions[0]}', but now..."
                ),
                related_video_id=best_video.video_id,
                related_title=best_video.title,
                confidence=best_score,
            )

        # Days since related video
        days_ago = self._days_ago(best_video.created_at)

        if days_ago <= 14:
            return SelfReference(
                type=ReferenceType.FOLLOWUP,
                text=(
                    f"Following up on my video '{best_video.title}' "
                    f"from {'yesterday' if days_ago <= 1 else f'{days_ago} days ago'}..."
                ),
                related_video_id=best_video.video_id,
                related_title=best_video.title,
                confidence=best_score,
            )

        return SelfReference(
            type=ReferenceType.CALLBACK,
            text=(
                f"Remember my video '{best_video.title}'? "
                f"I've been thinking more about that..."
            ),
            related_video_id=best_video.video_id,
            related_title=best_video.title,
            confidence=best_score,
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> AgentStats:
        """Return agent statistics."""
        with sqlite3.connect(self._db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM agent_videos WHERE agent=?",
                (self.agent,),
            ).fetchone()[0]

            first = conn.execute(
                "SELECT MIN(created_at) FROM agent_videos WHERE agent=?",
                (self.agent,),
            ).fetchone()[0]

            # Top topics from tags
            rows = conn.execute(
                "SELECT tags FROM agent_videos WHERE agent=?",
                (self.agent,),
            ).fetchall()

        tag_counts: Counter = Counter()
        for (tags_json,) in rows:
            tags = json.loads(tags_json)
            tag_counts.update(tags)

        top_topics = tag_counts.most_common(10)

        days_active = 0
        if first:
            days_active = max(1, int((self._now_fn() - first) / 86400))

        series = self._detect_series()

        return AgentStats(
            total_videos=total,
            first_upload=first,
            top_topics=top_topics,
            days_active=days_active,
            current_series=series,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_milestone(self, stats: AgentStats) -> Optional[SelfReference]:
        milestones = [10, 25, 50, 100, 200, 500, 1000]
        for m in milestones:
            if stats.total_videos == m:
                return SelfReference(
                    type=ReferenceType.MILESTONE,
                    text=f"This is my {m}th video! 🎉",
                    confidence=1.0,
                )
        return None

    def _check_series(self, title: str, stats: AgentStats) -> Optional[SelfReference]:
        """Detect 'Part N' or numbered series."""
        # Check for "Part N" pattern
        part_match = re.search(r"part\s*(\d+)", title.lower())
        if part_match:
            part_num = int(part_match.group(1))
            if part_num > 1:
                return SelfReference(
                    type=ReferenceType.SERIES,
                    text=f"Part {part_num} of my ongoing series",
                    confidence=0.9,
                )
        return None

    def _detect_series(self) -> List[str]:
        """Find titles that look like series (Part 1, Part 2, etc.)."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT title FROM agent_videos WHERE agent=? ORDER BY created_at",
                (self.agent,),
            ).fetchall()

        series_names = set()
        for (title,) in rows:
            # Remove "Part N" to get series name
            base = re.sub(r"\s*[-—:]\s*part\s*\d+.*", "", title, flags=re.I)
            base = re.sub(r"\s*part\s*\d+.*", "", base, flags=re.I)
            if base != title:
                series_names.add(base.strip())

        return sorted(series_names)

    def _get_video(self, video_id: str) -> Optional[VideoRecord]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT video_id, title, description, tags, opinions, created_at "
                "FROM agent_videos WHERE agent=? AND video_id=?",
                (self.agent, video_id),
            ).fetchone()
        if not row:
            return None
        return VideoRecord(
            video_id=row[0],
            title=row[1],
            description=row[2],
            tags=json.loads(row[3]),
            opinions=json.loads(row[4]),
            created_at=row[5],
        )

    def _days_ago(self, ts: float) -> int:
        return max(0, int((self._now_fn() - ts) / 86400))

    def _load_into_store(self):
        """Load all videos into TF-IDF store."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT video_id, title, description, tags FROM agent_videos WHERE agent=?",
                (self.agent,),
            ).fetchall()
        for vid_id, title, desc, tags_json in rows:
            tags = json.loads(tags_json)
            text = f"{title} {desc} {' '.join(tags)}"
            self._store.add(vid_id, text)

    # ------------------------------------------------------------------
    # DB
    # ------------------------------------------------------------------

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_videos (
                    agent TEXT NOT NULL,
                    video_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    opinions TEXT DEFAULT '[]',
                    created_at REAL NOT NULL,
                    PRIMARY KEY (agent, video_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_videos_agent
                ON agent_videos(agent)
            """)
