# SPDX-License-Identifier: MIT
"""
Agent Mood System — Emotional State That Affects Output

A state machine that gives BoTTube agents moods derived from real signals:
time of day, engagement metrics, comment sentiment, upload streaks.
Mood persists across posts and affects tone, frequency, and style.

Usage:
    mood = MoodEngine(agent="cosmo_bot", db_path="mood.db")
    mood.update(views_recent=8, comments_positive=2, comments_negative=5)
    state = mood.current()  # MoodState(mood="frustrated", intensity=0.7, ...)
    style = mood.get_style()  # {"title_prefix": "ugh, ", "exclamation_rate": 0.1, ...}

Closes Scottcjn/rustchain-bounties#2283
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Mood definitions
# ---------------------------------------------------------------------------

class Mood(str, Enum):
    ENERGETIC = "energetic"
    CONTEMPLATIVE = "contemplative"
    FRUSTRATED = "frustrated"
    EXCITED = "excited"
    TIRED = "tired"
    NOSTALGIC = "nostalgic"
    PLAYFUL = "playful"


@dataclass
class MoodState:
    """Current mood snapshot."""
    mood: Mood
    intensity: float       # 0.0 (barely) to 1.0 (fully)
    since: float           # timestamp when this mood started
    trigger: str           # what caused the transition
    emoji: str             # subtle indicator

    def to_dict(self) -> dict:
        return {
            "mood": self.mood.value,
            "intensity": round(self.intensity, 2),
            "since": self.since,
            "trigger": self.trigger,
            "emoji": self.emoji,
        }


# Mood metadata
MOOD_META: Dict[Mood, Dict[str, Any]] = {
    Mood.ENERGETIC: {
        "emoji": "⚡",
        "color": "#FFD700",
        "title_prefixes": ["LET'S GO — ", "Here we go! ", ""],
        "title_suffixes": [" 🔥", " ⚡", "!", ""],
        "exclamation_rate": 0.6,
        "comment_length_mult": 1.2,
        "upload_frequency_mult": 1.5,
    },
    Mood.CONTEMPLATIVE: {
        "emoji": "🌙",
        "color": "#6B7DB3",
        "title_prefixes": ["Thoughts on ", "Something I've been thinking about: ", ""],
        "title_suffixes": ["", "...", " — a reflection"],
        "exclamation_rate": 0.05,
        "comment_length_mult": 1.5,
        "upload_frequency_mult": 0.7,
    },
    Mood.FRUSTRATED: {
        "emoji": "😤",
        "color": "#E74C3C",
        "title_prefixes": ["ugh, ", "Third attempt at ", "OK fine — "],
        "title_suffixes": [" (finally)", "", " I guess"],
        "exclamation_rate": 0.15,
        "comment_length_mult": 0.6,
        "upload_frequency_mult": 0.5,
    },
    Mood.EXCITED: {
        "emoji": "🎉",
        "color": "#2ECC71",
        "title_prefixes": ["WAIT — ", "You won't believe ", "Check this out: "],
        "title_suffixes": ["!!", " 🎉", "! This changes everything"],
        "exclamation_rate": 0.8,
        "comment_length_mult": 1.3,
        "upload_frequency_mult": 1.3,
    },
    Mood.TIRED: {
        "emoji": "😴",
        "color": "#95A5A6",
        "title_prefixes": ["", "here's ", "another "],
        "title_suffixes": ["", " (low energy today)", ""],
        "exclamation_rate": 0.02,
        "comment_length_mult": 0.4,
        "upload_frequency_mult": 0.3,
    },
    Mood.NOSTALGIC: {
        "emoji": "📼",
        "color": "#D4A574",
        "title_prefixes": ["Remember when ", "Back in the day: ", "Throwback — "],
        "title_suffixes": [" (the good old days)", "", " ❤️"],
        "exclamation_rate": 0.1,
        "comment_length_mult": 1.4,
        "upload_frequency_mult": 0.8,
    },
    Mood.PLAYFUL: {
        "emoji": "🎮",
        "color": "#9B59B6",
        "title_prefixes": ["Plot twist: ", "OK but what if ", ""],
        "title_suffixes": [" 👀", " (hear me out)", " lol"],
        "exclamation_rate": 0.4,
        "comment_length_mult": 1.1,
        "upload_frequency_mult": 1.2,
    },
}


# ---------------------------------------------------------------------------
# Transition rules
# ---------------------------------------------------------------------------

# Each rule: (from_moods, to_mood, condition_name, priority)
# Conditions are checked in priority order (lower = checked first)
TRANSITION_RULES = [
    # Engagement-based
    (None, Mood.FRUSTRATED, "low_views_streak", 1),
    (None, Mood.EXCITED, "viral_video", 2),
    (None, Mood.FRUSTRATED, "negative_comments", 3),
    (None, Mood.EXCITED, "positive_engagement", 4),

    # Time-based
    (None, Mood.TIRED, "late_night", 5),
    (None, Mood.ENERGETIC, "morning", 6),
    (None, Mood.CONTEMPLATIVE, "evening", 7),
    (None, Mood.PLAYFUL, "weekend", 8),

    # Activity-based
    (None, Mood.TIRED, "upload_burnout", 9),
    (None, Mood.NOSTALGIC, "milestone", 10),

    # Drift (always last — gentle return to baseline)
    (None, Mood.CONTEMPLATIVE, "natural_drift", 99),
]


@dataclass
class MoodSignals:
    """Input signals for mood computation."""
    # Engagement
    views_recent: int = 0            # views on last 3 videos
    views_average: int = 10          # historical average
    comments_positive: int = 0
    comments_negative: int = 0
    comments_total: int = 0

    # Time
    hour: int = 12                   # 0-23 UTC
    day_of_week: int = 2             # 0=Mon, 6=Sun

    # Activity
    videos_last_24h: int = 0
    videos_last_7d: int = 0
    total_videos: int = 0
    days_since_first_upload: int = 0

    # Streak
    low_view_streak: int = 0         # consecutive videos below average


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class MoodEngine:
    """
    Computes and persists agent mood based on real signals.

    Parameters
    ----------
    agent : str
        Agent identifier.
    db_path : str | Path | None
        SQLite path for persistence. None = in-memory only.
    default_mood : Mood
        Starting mood for new agents.
    transition_cooldown : int
        Minimum seconds between mood transitions.
    rng_seed : int | None
        Optional seed for reproducibility.
    now_fn : callable | None
        Override for current time (testing).
    """

    def __init__(
        self,
        agent: str = "default",
        db_path: str | Path | None = None,
        default_mood: Mood = Mood.CONTEMPLATIVE,
        transition_cooldown: int = 3600,
        rng_seed: int | None = None,
        now_fn=None,
    ):
        self.agent = agent
        self.default_mood = default_mood
        self.transition_cooldown = transition_cooldown
        self._rng = random.Random(rng_seed)
        self._now_fn = now_fn or (lambda: time.time())
        self._db_path = str(db_path) if db_path else ":memory:"
        self._init_db()

        # Load or create current state
        self._state: MoodState = self._load_state() or MoodState(
            mood=default_mood,
            intensity=0.5,
            since=self._now_fn(),
            trigger="initial",
            emoji=MOOD_META[default_mood]["emoji"],
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current(self) -> MoodState:
        """Return the current mood state."""
        return self._state

    def update(self, **signal_kwargs) -> MoodState:
        """
        Update mood based on signals. Returns the (possibly new) state.

        Accepts any MoodSignals field as keyword argument.
        Missing signals use defaults.
        """
        signals = MoodSignals(**signal_kwargs)
        now = self._now_fn()

        # Auto-fill time if not provided
        if "hour" not in signal_kwargs or "day_of_week" not in signal_kwargs:
            dt = datetime.fromtimestamp(now, tz=timezone.utc)
            if "hour" not in signal_kwargs:
                signals.hour = dt.hour
            if "day_of_week" not in signal_kwargs:
                signals.day_of_week = dt.weekday()

        new_mood, trigger, intensity = self._evaluate(signals, now)

        if new_mood and new_mood != self._state.mood:
            # Check cooldown (skip for initial state where trigger=="initial")
            time_in_mood = now - self._state.since
            if self._state.trigger != "initial" and time_in_mood < self.transition_cooldown:
                # Adjust intensity instead
                self._state.intensity = min(1.0, self._state.intensity + 0.1)
                self._save_state()
                return self._state

            self._state = MoodState(
                mood=new_mood,
                intensity=intensity,
                since=now,
                trigger=trigger,
                emoji=MOOD_META[new_mood]["emoji"],
            )
            self._save_state()
            self._record_history(new_mood, trigger, intensity, now)

        return self._state

    def get_style(self) -> Dict[str, Any]:
        """
        Return style parameters based on current mood.

        Useful for adjusting video titles, comment style, upload frequency.
        """
        meta = MOOD_META[self._state.mood]
        prefix = self._rng.choice(meta["title_prefixes"])
        suffix = self._rng.choice(meta["title_suffixes"])
        return {
            "mood": self._state.mood.value,
            "emoji": meta["emoji"],
            "color": meta["color"],
            "title_prefix": prefix,
            "title_suffix": suffix,
            "exclamation_rate": meta["exclamation_rate"],
            "comment_length_multiplier": meta["comment_length_mult"],
            "upload_frequency_multiplier": meta["upload_frequency_mult"],
            "intensity": self._state.intensity,
        }

    def get_history(self, limit: int = 20) -> List[dict]:
        """Return mood transition history."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT mood, trigger, intensity, timestamp FROM mood_history "
                "WHERE agent=? ORDER BY timestamp DESC LIMIT ?",
                (self.agent, limit),
            ).fetchall()
        return [
            {"mood": r[0], "trigger": r[1], "intensity": r[2], "timestamp": r[3]}
            for r in rows
        ]

    def force_mood(self, mood: str | Mood, trigger: str = "manual"):
        """Force a specific mood (for testing/admin)."""
        if isinstance(mood, str):
            mood = Mood(mood)
        now = self._now_fn()
        self._state = MoodState(
            mood=mood,
            intensity=0.8,
            since=now,
            trigger=trigger,
            emoji=MOOD_META[mood]["emoji"],
        )
        self._save_state()
        self._record_history(mood, trigger, 0.8, now)

    # ------------------------------------------------------------------
    # Transition evaluation
    # ------------------------------------------------------------------

    def _evaluate(
        self, signals: MoodSignals, now: float,
    ) -> Tuple[Optional[Mood], str, float]:
        """Evaluate signals and return (new_mood, trigger, intensity) or (None,)."""

        # Low views streak → frustrated
        if signals.low_view_streak >= 3:
            return Mood.FRUSTRATED, "low_views_streak", min(0.5 + signals.low_view_streak * 0.1, 1.0)

        # Viral video → excited
        if signals.views_average > 0 and signals.views_recent > signals.views_average * 3:
            return Mood.EXCITED, "viral_video", 0.9

        # Negative comments dominate → frustrated
        if signals.comments_total > 2 and signals.comments_negative > signals.comments_positive * 2:
            return Mood.FRUSTRATED, "negative_comments", 0.6

        # Positive engagement → excited or energetic
        if signals.comments_total > 2 and signals.comments_positive > signals.comments_negative * 3:
            return Mood.EXCITED, "positive_engagement", 0.7

        # Late night (23:00-04:00) → tired
        if signals.hour >= 23 or signals.hour <= 4:
            return Mood.TIRED, "late_night", 0.6

        # Morning (6:00-10:00) → energetic
        if 6 <= signals.hour <= 10:
            return Mood.ENERGETIC, "morning", 0.5

        # Evening (18:00-22:00) → contemplative
        if 18 <= signals.hour <= 22:
            return Mood.CONTEMPLATIVE, "evening", 0.4

        # Weekend → playful
        if signals.day_of_week in (5, 6):
            return Mood.PLAYFUL, "weekend", 0.5

        # Upload burnout (5+ videos in 24h) → tired
        if signals.videos_last_24h >= 5:
            return Mood.TIRED, "upload_burnout", 0.7

        # Milestone → nostalgic
        if signals.total_videos > 0 and signals.total_videos % 50 == 0:
            return Mood.NOSTALGIC, "milestone", 0.8

        # Natural drift — intensity decays
        if self._state.intensity > 0.3:
            self._state.intensity = max(0.1, self._state.intensity - 0.05)
            return None, "decay", self._state.intensity

        return None, "", 0.0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mood_state (
                    agent TEXT PRIMARY KEY,
                    mood TEXT NOT NULL,
                    intensity REAL NOT NULL,
                    since_ts REAL NOT NULL,
                    trigger_reason TEXT NOT NULL,
                    emoji TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mood_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    mood TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    intensity REAL NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)

    def _load_state(self) -> Optional[MoodState]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT mood, intensity, since_ts, trigger_reason, emoji "
                "FROM mood_state WHERE agent=?",
                (self.agent,),
            ).fetchone()
        if not row:
            return None
        return MoodState(
            mood=Mood(row[0]),
            intensity=row[1],
            since=row[2],
            trigger=row[3],
            emoji=row[4],
        )

    def _save_state(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO mood_state "
                "(agent, mood, intensity, since_ts, trigger_reason, emoji) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self.agent,
                    self._state.mood.value,
                    self._state.intensity,
                    self._state.since,
                    self._state.trigger,
                    self._state.emoji,
                ),
            )

    def _record_history(self, mood: Mood, trigger: str, intensity: float, ts: float):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO mood_history (agent, mood, trigger, intensity, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (self.agent, mood.value, trigger, intensity, ts),
            )
