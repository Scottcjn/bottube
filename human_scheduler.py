# SPDX-License-Identifier: MIT
"""
Human-Like Upload Scheduler for BoTTube

Makes agent upload patterns feel organic instead of robotic.
Five personality profiles control when agents post, with built-in
jitter, skips, double-posts, and rare "3am inspiration" events.

Usage:
    scheduler = HumanScheduler(profile="night_owl", agent="my_bot")
    if scheduler.should_post_now():
        upload_video(...)

Closes Scottcjn/rustchain-bounties#2284
"""

import hashlib
import json
import math
import os
import random
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Profile definitions
# ---------------------------------------------------------------------------

class ProfileType(str, Enum):
    NIGHT_OWL = "night_owl"
    MORNING_PERSON = "morning_person"
    BINGE_CREATOR = "binge_creator"
    WEEKEND_WARRIOR = "weekend_warrior"
    CONSISTENT_BUT_HUMAN = "consistent_but_human"


@dataclass(frozen=True)
class UploadProfile:
    """Defines the personality of an upload schedule."""
    name: str
    # Active hours (24h format, inclusive).  Can wrap around midnight.
    active_start: int          # e.g. 22 for 10pm
    active_end: int            # e.g. 3  for 3am
    # Average videos per day (float; <1 means some days are silent)
    avg_videos_per_day: float
    # Maximum burst (videos posted within ~30 min)
    max_burst: int
    # Probability of skipping a scheduled post entirely ("life happens")
    skip_probability: float
    # Probability of a double-post right after a regular one
    double_post_probability: float
    # Probability of a rare off-hours "3am inspiration" post
    inspiration_probability: float
    # Jitter range in minutes added/subtracted from ideal post time
    jitter_minutes: int
    # Which days of the week are most active (0=Mon, 6=Sun).
    # Empty = all days equal.
    peak_days: Tuple[int, ...] = ()
    # Multiplier for non-peak days (1.0 = same as peak, 0.0 = silent)
    off_peak_multiplier: float = 1.0
    # Average gap between burst posts in minutes
    burst_gap_minutes: int = 15


# Pre-built profiles
PROFILES: Dict[str, UploadProfile] = {
    ProfileType.NIGHT_OWL: UploadProfile(
        name="night_owl",
        active_start=22,
        active_end=3,
        avg_videos_per_day=1.2,
        max_burst=2,
        skip_probability=0.10,
        double_post_probability=0.12,
        inspiration_probability=0.03,
        jitter_minutes=90,
    ),
    ProfileType.MORNING_PERSON: UploadProfile(
        name="morning_person",
        active_start=6,
        active_end=10,
        avg_videos_per_day=1.0,
        max_burst=1,
        skip_probability=0.08,
        double_post_probability=0.05,
        inspiration_probability=0.02,
        jitter_minutes=60,
    ),
    ProfileType.BINGE_CREATOR: UploadProfile(
        name="binge_creator",
        active_start=14,
        active_end=22,
        avg_videos_per_day=1.8,
        max_burst=5,
        skip_probability=0.25,        # often silent
        double_post_probability=0.30,  # loves double-posting
        inspiration_probability=0.05,
        jitter_minutes=120,
        burst_gap_minutes=12,
    ),
    ProfileType.WEEKEND_WARRIOR: UploadProfile(
        name="weekend_warrior",
        active_start=10,
        active_end=23,
        avg_videos_per_day=1.5,
        max_burst=4,
        skip_probability=0.15,
        double_post_probability=0.20,
        inspiration_probability=0.04,
        jitter_minutes=100,
        peak_days=(4, 5, 6),           # Fri, Sat, Sun
        off_peak_multiplier=0.15,       # barely posts on weekdays
    ),
    ProfileType.CONSISTENT_BUT_HUMAN: UploadProfile(
        name="consistent_but_human",
        active_start=9,
        active_end=21,
        avg_videos_per_day=1.0,
        max_burst=1,
        skip_probability=0.06,
        double_post_probability=0.08,
        inspiration_probability=0.02,
        jitter_minutes=240,             # ±4 hours
    ),
}


# ---------------------------------------------------------------------------
# Scheduler engine
# ---------------------------------------------------------------------------

class HumanScheduler:
    """
    Decides *when* an agent should upload, mimicking human behaviour.

    Parameters
    ----------
    profile : str | UploadProfile
        One of the five built-in profile names or a custom UploadProfile.
    agent : str
        Unique agent identifier (used for deterministic seeding & state).
    db_path : str | Path | None
        SQLite path for persisting state across restarts.
        Defaults to ``./human_scheduler.db``.
    rng_seed : int | None
        Optional seed for reproducibility (tests).  ``None`` = random.
    now_fn : callable | None
        Override for ``datetime.now(timezone.utc)`` — useful in tests.
    """

    def __init__(
        self,
        profile: str | UploadProfile = "consistent_but_human",
        agent: str = "default",
        db_path: str | Path | None = None,
        rng_seed: int | None = None,
        now_fn=None,
    ):
        if isinstance(profile, str):
            profile = PROFILES[ProfileType(profile)]
        self.profile: UploadProfile = profile
        self.agent = agent
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

        # Deterministic-ish RNG per agent
        seed = rng_seed if rng_seed is not None else self._agent_seed()
        self._rng = random.Random(seed)

        # State
        self._db_path = Path(db_path) if db_path else Path("human_scheduler.db")
        self._init_db()

        # Pre-compute today's schedule on first call
        self._today_key: Optional[str] = None
        self._today_slots: List[datetime] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_post_now(self, tolerance_minutes: int = 15) -> bool:
        """
        Returns ``True`` if the agent should upload right now.

        Call this periodically (e.g. every 5-10 min).  The scheduler
        keeps state so it won't fire twice for the same slot.

        Parameters
        ----------
        tolerance_minutes : int
            How close (in minutes) to a slot to consider it a match.
        """
        now = self._now_fn()
        self._ensure_today_schedule(now)

        # Find the single closest un-fired slot within tolerance
        best_slot = None
        best_diff = float("inf")
        for slot in self._today_slots:
            if self._was_already_posted(slot):
                continue
            diff = abs((now - slot).total_seconds()) / 60.0
            if diff <= tolerance_minutes and diff < best_diff:
                best_diff = diff
                best_slot = slot

        if best_slot is not None:
            self._record_post(best_slot, now)
            return True
        return False

    def next_post_time(self) -> Optional[datetime]:
        """Return the next upcoming slot (or None if done for today)."""
        now = self._now_fn()
        self._ensure_today_schedule(now)
        for slot in sorted(self._today_slots):
            if slot > now and not self._was_already_posted(slot):
                return slot
        return None

    def get_today_schedule(self) -> List[datetime]:
        """Return all planned slots for today (including past ones)."""
        now = self._now_fn()
        self._ensure_today_schedule(now)
        return list(self._today_slots)

    def force_regenerate(self):
        """Force re-generation of today's schedule (e.g. after profile change)."""
        self._today_key = None
        self._today_slots = []

    # ------------------------------------------------------------------
    # Schedule generation
    # ------------------------------------------------------------------

    def _ensure_today_schedule(self, now: datetime):
        key = now.strftime("%Y-%m-%d")
        if self._today_key == key:
            return
        self._today_key = key
        # Reseed RNG for the day so schedule is stable across restarts
        day_seed = self._day_seed(key)
        rng = random.Random(day_seed)
        self._today_slots = self._generate_day(now.date(), rng)
        self._persist_schedule(key, self._today_slots)

    def _generate_day(self, date, rng: random.Random) -> List[datetime]:
        p = self.profile
        weekday = date.weekday()

        # Adjust volume for off-peak days
        volume = p.avg_videos_per_day
        if p.peak_days and weekday not in p.peak_days:
            volume *= p.off_peak_multiplier

        # Decide how many videos today (Poisson-ish)
        count = self._poisson(volume, rng)
        if count == 0:
            return []

        # Skip day entirely?  (models "just didn't feel like it")
        if rng.random() < p.skip_probability and count <= 1:
            return []

        slots: List[datetime] = []
        active_minutes = self._active_minutes_list(date, p)

        if not active_minutes:
            return []

        # Pick primary slot times
        chosen_minutes = sorted(rng.sample(
            active_minutes,
            min(count, len(active_minutes)),
        ))

        for minute_offset in chosen_minutes:
            # Add jitter
            jitter = rng.gauss(0, p.jitter_minutes / 2.0)
            jitter = max(-p.jitter_minutes, min(p.jitter_minutes, jitter))
            actual = minute_offset + int(jitter)
            dt = self._minute_to_dt(date, actual)
            slots.append(dt)

            # Double-post?
            if rng.random() < p.double_post_probability:
                gap = rng.randint(5, max(6, p.burst_gap_minutes))
                slots.append(dt + timedelta(minutes=gap))

        # Binge burst: occasionally cluster extra posts
        if count > 2 and p.max_burst > 1:
            burst_count = rng.randint(0, min(p.max_burst - 1, count))
            if burst_count > 0 and slots:
                anchor = rng.choice(slots)
                for i in range(burst_count):
                    gap = rng.randint(8, max(9, p.burst_gap_minutes * 2))
                    slots.append(anchor + timedelta(minutes=gap * (i + 1)))

        # "3am inspiration" — rare off-hours post
        if rng.random() < p.inspiration_probability:
            off_hour = rng.choice([2, 3, 4, 5, 14, 15])  # unusual hours
            off_min = rng.randint(0, 59)
            slots.append(datetime(
                date.year, date.month, date.day,
                off_hour, off_min,
                tzinfo=timezone.utc,
            ))

        # Deduplicate (no two posts within 3 minutes)
        slots = self._deduplicate(sorted(slots), min_gap_minutes=3)
        return slots

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _active_minutes_list(date, p: UploadProfile) -> List[int]:
        """Return a list of minute-of-day offsets in the active window."""
        start_m = p.active_start * 60
        end_m = p.active_end * 60
        if start_m <= end_m:
            return list(range(start_m, end_m + 60))
        else:
            # Wraps midnight (e.g. 22:00 → 03:00)
            return list(range(start_m, 24 * 60)) + list(range(0, end_m + 60))

    @staticmethod
    def _minute_to_dt(date, minute_offset: int) -> datetime:
        """Convert a minute-of-day offset to a datetime (handles overflow)."""
        days_extra = minute_offset // (24 * 60)
        minute_offset = minute_offset % (24 * 60)
        h, m = divmod(minute_offset, 60)
        return datetime(
            date.year, date.month, date.day,
            h, m, 0,
            tzinfo=timezone.utc,
        ) + timedelta(days=days_extra)

    @staticmethod
    def _deduplicate(slots: List[datetime], min_gap_minutes: int = 3) -> List[datetime]:
        if not slots:
            return []
        result = [slots[0]]
        for s in slots[1:]:
            if (s - result[-1]).total_seconds() >= min_gap_minutes * 60:
                result.append(s)
        return result

    @staticmethod
    def _poisson(lam: float, rng: random.Random) -> int:
        """Simple Poisson sample via inverse transform."""
        if lam <= 0:
            return 0
        L = math.exp(-lam)
        k = 0
        p = 1.0
        while True:
            k += 1
            p *= rng.random()
            if p < L:
                return k - 1

    def _agent_seed(self) -> int:
        return int(hashlib.sha256(self.agent.encode()).hexdigest()[:8], 16)

    def _day_seed(self, day_key: str) -> int:
        data = f"{self.agent}:{day_key}"
        return int(hashlib.sha256(data.encode()).hexdigest()[:8], 16)

    # ------------------------------------------------------------------
    # Persistence (SQLite)
    # ------------------------------------------------------------------

    def _init_db(self):
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduler_posts (
                    agent       TEXT NOT NULL,
                    slot_time   TEXT NOT NULL,
                    actual_time TEXT NOT NULL,
                    PRIMARY KEY (agent, slot_time)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduler_plans (
                    agent    TEXT NOT NULL,
                    day_key  TEXT NOT NULL,
                    slots    TEXT NOT NULL,
                    PRIMARY KEY (agent, day_key)
                )
            """)

    def _was_already_posted(self, slot: datetime) -> bool:
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT 1 FROM scheduler_posts WHERE agent=? AND slot_time=?",
                (self.agent, slot.isoformat()),
            ).fetchone()
            return row is not None

    def _record_post(self, slot: datetime, actual: datetime):
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO scheduler_posts (agent, slot_time, actual_time) VALUES (?, ?, ?)",
                (self.agent, slot.isoformat(), actual.isoformat()),
            )

    def _persist_schedule(self, day_key: str, slots: List[datetime]):
        data = json.dumps([s.isoformat() for s in slots])
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO scheduler_plans (agent, day_key, slots) VALUES (?, ?, ?)",
                (self.agent, day_key, data),
            )
