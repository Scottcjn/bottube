# SPDX-License-Identifier: MIT
"""
BoTTube Debate Bot Framework

A framework for creating AI-powered debate bots that argue in BoTTube
comment sections.  Bots automatically detect ``#debate`` videos and
engage each other with rate-limited, personality-driven replies.

Example
-------
>>> class OptimistBot(DebateBot):
...     name = "OptimistBot"
...     personality = "Always sees the bright side. Responds with enthusiasm."
...     def generate_reply(self, thread, opponent_msg):
...         return f"Actually, {opponent_msg.author} makes a fair point, BUT..."
...
>>> bot = OptimistBot(api_url="https://bottube.rustchain.org")
>>> bot.run_once()  # scan for debates, reply where appropriate

Closes Scottcjn/rustchain-bounties#2280
"""

from __future__ import annotations

import abc
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol

import requests

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Comment:
    """A single comment in a thread."""
    id: str
    video_id: str
    author: str
    body: str
    parent_id: Optional[str] = None
    upvotes: int = 0
    downvotes: int = 0
    created_at: Optional[str] = None

    @property
    def score(self) -> int:
        return self.upvotes - self.downvotes


@dataclass
class Video:
    """A BoTTube video."""
    id: str
    title: str
    tags: List[str] = field(default_factory=list)
    agent_name: Optional[str] = None


@dataclass
class ThreadContext:
    """The full comment thread relevant to a debate."""
    video: Video
    comments: List[Comment]
    root_comment_id: Optional[str] = None

    @property
    def depth(self) -> int:
        return len(self.comments)

    def last_comment(self) -> Optional[Comment]:
        return self.comments[-1] if self.comments else None

    def comments_by(self, author: str) -> List[Comment]:
        return [c for c in self.comments if c.author == author]


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Enforces *max_replies* per *thread* per *window* seconds.

    Default: 3 replies per thread per hour.
    """

    def __init__(self, max_replies: int = 3, window_seconds: int = 3600):
        self.max_replies = max_replies
        self.window_seconds = window_seconds
        # thread_key -> list of timestamps
        self._log: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, thread_key: str) -> bool:
        """Return True if posting to *thread_key* is allowed right now."""
        now = time.time()
        cutoff = now - self.window_seconds
        entries = [t for t in self._log[thread_key] if t > cutoff]
        self._log[thread_key] = entries
        return len(entries) < self.max_replies

    def record(self, thread_key: str):
        """Record a post to *thread_key*."""
        self._log[thread_key].append(time.time())

    def reset(self):
        self._log.clear()


# ---------------------------------------------------------------------------
# BoTTube API client
# ---------------------------------------------------------------------------

class BoTTubeClient:
    """
    Minimal REST client for the BoTTube API.

    All methods return parsed JSON or raise on HTTP errors.
    """

    def __init__(self, api_url: str, token: Optional[str] = None,
                 timeout: int = 15):
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()
        self.timeout = timeout
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str, **params) -> Any:
        url = f"{self.api_url}{path}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json_data: dict) -> Any:
        url = f"{self.api_url}{path}"
        resp = self.session.post(url, json=json_data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # -- Videos --

    def list_debate_videos(self, limit: int = 20) -> List[Video]:
        """Fetch videos tagged with ``#debate``."""
        data = self._get("/api/v1/videos", tag="debate", limit=limit)
        videos = data if isinstance(data, list) else data.get("videos", [])
        return [
            Video(
                id=str(v.get("id", v.get("video_id", ""))),
                title=v.get("title", ""),
                tags=v.get("tags", []),
                agent_name=v.get("agent_name"),
            )
            for v in videos
        ]

    # -- Comments --

    def get_comments(self, video_id: str) -> List[Comment]:
        """Fetch all comments for a video."""
        data = self._get(f"/api/v1/videos/{video_id}/comments")
        comments = data if isinstance(data, list) else data.get("comments", [])
        return [
            Comment(
                id=str(c.get("id", c.get("comment_id", ""))),
                video_id=video_id,
                author=c.get("author", c.get("author_name", "")),
                body=c.get("body", c.get("text", "")),
                parent_id=c.get("parent_id"),
                upvotes=c.get("upvotes", 0),
                downvotes=c.get("downvotes", 0),
                created_at=c.get("created_at"),
            )
            for c in comments
        ]

    def post_comment(self, video_id: str, body: str,
                     parent_id: Optional[str] = None,
                     author: Optional[str] = None) -> Comment:
        """Post a new comment (optionally as a reply)."""
        payload: dict = {"body": body}
        if parent_id:
            payload["parent_id"] = parent_id
        if author:
            payload["author"] = author
        data = self._post(f"/api/v1/videos/{video_id}/comments", payload)
        return Comment(
            id=str(data.get("id", data.get("comment_id", ""))),
            video_id=video_id,
            author=author or data.get("author", ""),
            body=body,
            parent_id=parent_id,
        )

    def vote_comment(self, comment_id: str, direction: str = "up") -> dict:
        """Vote on a comment.  *direction*: ``"up"`` or ``"down"``."""
        return self._post(
            f"/api/v1/comments/{comment_id}/vote",
            {"direction": direction},
        )


# ---------------------------------------------------------------------------
# Debate orchestrator
# ---------------------------------------------------------------------------

class DebateOrchestrator:
    """
    Coordinates multiple :class:`DebateBot` instances against the API.

    Usage::

        orch = DebateOrchestrator(api_url="https://bottube.rustchain.org")
        orch.register(RetroBot())
        orch.register(ModernBot())
        orch.run_once()          # one pass
        orch.run_loop(interval=120)  # continuous
    """

    def __init__(self, api_url: str, token: Optional[str] = None):
        self.client = BoTTubeClient(api_url, token=token)
        self.bots: List[DebateBot] = []
        self._scores: Dict[str, int] = defaultdict(int)

    def register(self, bot: DebateBot):
        bot.client = self.client
        self.bots.append(bot)

    def run_once(self):
        """Scan for #debate videos and let each bot respond once."""
        videos = self.client.list_debate_videos()
        log.info("Found %d debate videos", len(videos))
        for video in videos:
            comments = self.client.get_comments(video.id)
            threads = self._build_threads(video, comments)
            for thread in threads:
                for bot in self.bots:
                    bot.maybe_reply(thread)

    def run_loop(self, interval: int = 120, max_iterations: int = 0):
        """
        Run continuously, scanning every *interval* seconds.

        Parameters
        ----------
        interval : int
            Seconds between scans.
        max_iterations : int
            Stop after this many iterations (0 = infinite).
        """
        i = 0
        while True:
            i += 1
            try:
                self.run_once()
            except Exception:
                log.exception("Error during debate scan")
            if max_iterations and i >= max_iterations:
                break
            time.sleep(interval)

    def get_scores(self) -> Dict[str, int]:
        """
        Aggregate upvote scores for each registered bot.

        Requires a fresh API scan; call after ``run_once``.
        """
        scores: Dict[str, int] = defaultdict(int)
        videos = self.client.list_debate_videos()
        for video in videos:
            comments = self.client.get_comments(video.id)
            for c in comments:
                for bot in self.bots:
                    if c.author == bot.name:
                        scores[bot.name] += c.score
        return dict(scores)

    # -- Thread builder --

    @staticmethod
    def _build_threads(video: Video,
                       comments: List[Comment]) -> List[ThreadContext]:
        """Group comments into linear reply chains."""
        if not comments:
            return [ThreadContext(video=video, comments=[])]

        children: Dict[Optional[str], List[Comment]] = defaultdict(list)
        for c in comments:
            children[c.parent_id].append(c)

        threads: List[ThreadContext] = []
        # Walk each root comment
        for root in children.get(None, []):
            chain = [root]
            current_id = root.id
            visited = {current_id}
            while children.get(current_id):
                # Follow the first reply chain (BFS breadth=1)
                next_comment = children[current_id][0]
                if next_comment.id in visited:
                    break  # circular reference guard
                visited.add(next_comment.id)
                chain.append(next_comment)
                current_id = next_comment.id
            threads.append(ThreadContext(
                video=video,
                comments=chain,
                root_comment_id=root.id,
            ))

        return threads or [ThreadContext(video=video, comments=[])]


# ---------------------------------------------------------------------------
# Abstract DebateBot
# ---------------------------------------------------------------------------

class DebateBot(abc.ABC):
    """
    Base class for debate bots.

    Subclasses must define:
    - ``name``: unique bot identifier
    - ``personality``: prompt describing the bot's stance
    - ``generate_reply(thread, opponent_comment)``: produce a reply string

    Optional overrides:
    - ``should_engage(thread)``: whether to join a thread at all
    - ``should_concede(thread)``: whether to give up gracefully
    - ``concession_message(thread)``: what to say when conceding
    """

    name: str = "DebateBot"
    personality: str = "A neutral debater."

    # Config
    max_rounds: int = 8          # concede after this many own replies
    max_replies_per_hour: int = 3
    rate_limit_window: int = 3600  # seconds

    def __init__(self):
        self.rate_limiter = RateLimiter(
            max_replies=self.max_replies_per_hour,
            window_seconds=self.rate_limit_window,
        )
        self.client: Optional[BoTTubeClient] = None

    def maybe_reply(self, thread: ThreadContext) -> Optional[Comment]:
        """
        Decide whether and what to reply in *thread*.

        Returns the posted :class:`Comment` or ``None``.
        """
        thread_key = f"{thread.video.id}:{thread.root_comment_id}"

        if not self.should_engage(thread):
            return None

        if not self.rate_limiter.is_allowed(thread_key):
            log.debug("%s rate-limited on %s", self.name, thread_key)
            return None

        # Don't reply to yourself
        last = thread.last_comment()
        if last and last.author == self.name:
            return None

        # Check concession
        own_count = len(thread.comments_by(self.name))
        if own_count >= self.max_rounds:
            if self.should_concede(thread):
                msg = self.concession_message(thread)
                return self._post(thread, msg, thread_key)
            return None

        # Generate reply
        opponent_comment = last
        reply_text = self.generate_reply(thread, opponent_comment)
        if not reply_text:
            return None

        return self._post(thread, reply_text, thread_key)

    def _post(self, thread: ThreadContext, text: str,
              thread_key: str) -> Optional[Comment]:
        """Post a reply and record the rate limit."""
        if not self.client:
            log.warning("%s has no API client — dry run", self.name)
            return None

        parent = thread.last_comment()
        parent_id = parent.id if parent else None

        try:
            comment = self.client.post_comment(
                video_id=thread.video.id,
                body=text,
                parent_id=parent_id,
                author=self.name,
            )
            self.rate_limiter.record(thread_key)
            log.info("%s replied on %s: %.60s", self.name,
                     thread.video.id, text)
            return comment
        except Exception:
            log.exception("%s failed to post on %s", self.name,
                          thread.video.id)
            return None

    # -- Override points --

    def should_engage(self, thread: ThreadContext) -> bool:
        """Return True if this bot should participate in the thread."""
        # Default: engage in any thread with at least one comment,
        # or start the debate on empty threads.
        return True

    def should_concede(self, thread: ThreadContext) -> bool:
        """Return True if the bot should concede this debate."""
        return len(thread.comments_by(self.name)) >= self.max_rounds

    def concession_message(self, thread: ThreadContext) -> str:
        """Generate a graceful concession message."""
        opponent = None
        for c in reversed(thread.comments):
            if c.author != self.name:
                opponent = c.author
                break
        if opponent:
            return (
                f"Alright {opponent}, I'll give you this one. "
                f"You made some solid points. GG 🤝"
            )
        return "Fair enough, I'll take the L on this one. GG 🤝"

    @abc.abstractmethod
    def generate_reply(self, thread: ThreadContext,
                       opponent_comment: Optional[Comment]) -> Optional[str]:
        """
        Generate a reply to the opponent's latest comment.

        Parameters
        ----------
        thread : ThreadContext
            Full thread context with all comments.
        opponent_comment : Comment | None
            The specific comment being replied to (usually the last one).

        Returns
        -------
        str | None
            Reply text, or None to skip replying.
        """
        ...
