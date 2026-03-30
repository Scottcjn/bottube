# SPDX-License-Identifier: MIT
"""
Tests for human_scheduler.py — HumanScheduler

Validates that upload distributions are non-uniform and realistic,
profiles produce distinct patterns, and the scheduling engine
handles edge cases correctly.
"""

import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Allow import from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from human_scheduler import (
    PROFILES,
    HumanScheduler,
    ProfileType,
    UploadProfile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary SQLite path."""
    return tmp_path / "test_scheduler.db"


def make_now(year=2026, month=3, day=25, hour=12, minute=0):
    """Create a fixed UTC datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def make_scheduler(profile="consistent_but_human", agent="test_agent",
                   db_path=None, seed=42, now=None):
    """Helper to build a scheduler with deterministic settings."""
    if db_path is None:
        db_path = Path(tempfile.mktemp(suffix=".db"))
    now_fn = (lambda: now) if now else (lambda: make_now())
    return HumanScheduler(
        profile=profile,
        agent=agent,
        db_path=db_path,
        rng_seed=seed,
        now_fn=now_fn,
    )


# ---------------------------------------------------------------------------
# Profile basics
# ---------------------------------------------------------------------------

class TestProfiles:
    def test_all_five_profiles_exist(self):
        assert len(PROFILES) == 5
        for pt in ProfileType:
            assert pt in PROFILES

    def test_profile_names_match_enum(self):
        for pt, prof in PROFILES.items():
            assert prof.name == pt.value

    def test_avg_videos_per_day_positive(self):
        for prof in PROFILES.values():
            assert prof.avg_videos_per_day > 0


# ---------------------------------------------------------------------------
# Schedule generation
# ---------------------------------------------------------------------------

class TestScheduleGeneration:
    def test_consistent_profile_generates_roughly_one_per_day(self, tmp_db):
        """Over 30 days, consistent_but_human averages ~1 video/day."""
        counts = []
        for day_offset in range(30):
            now = make_now(day=1) + timedelta(days=day_offset)
            s = make_scheduler("consistent_but_human", db_path=tmp_db,
                               seed=day_offset, now=now)
            schedule = s.get_today_schedule()
            counts.append(len(schedule))
        avg = sum(counts) / len(counts)
        # Should be between 0.3 and 2.5
        assert 0.3 <= avg <= 2.5, f"avg={avg}"

    def test_binge_creator_has_burst_days(self, tmp_db):
        """Binge creators sometimes produce 3+ videos in a single day."""
        max_count = 0
        for day_offset in range(30):
            now = make_now(day=1) + timedelta(days=day_offset)
            s = make_scheduler("binge_creator", db_path=tmp_db,
                               seed=day_offset, now=now)
            schedule = s.get_today_schedule()
            max_count = max(max_count, len(schedule))
        assert max_count >= 3, f"max_count={max_count}"

    def test_binge_creator_has_silent_days(self, tmp_db):
        """Binge creators also have zero-video days."""
        has_zero = False
        for day_offset in range(30):
            now = make_now(day=1) + timedelta(days=day_offset)
            s = make_scheduler("binge_creator", db_path=tmp_db,
                               seed=day_offset, now=now)
            if len(s.get_today_schedule()) == 0:
                has_zero = True
                break
        assert has_zero, "Expected at least one silent day in 30 days"

    def test_night_owl_posts_late(self, tmp_db):
        """Night owl slots should cluster around 22:00-03:00."""
        late_count = 0
        total = 0
        for day_offset in range(30):
            now = make_now(day=1) + timedelta(days=day_offset)
            s = make_scheduler("night_owl", db_path=tmp_db,
                               seed=day_offset, now=now)
            for slot in s.get_today_schedule():
                total += 1
                h = slot.hour
                if h >= 20 or h <= 5:  # generous window for jitter
                    late_count += 1
        if total > 0:
            assert late_count / total >= 0.60, (
                f"Only {late_count}/{total} slots were late-night"
            )

    def test_morning_person_posts_early(self, tmp_db):
        """Morning person slots should cluster around 06:00-12:00."""
        early_count = 0
        total = 0
        for day_offset in range(30):
            now = make_now(day=1) + timedelta(days=day_offset)
            s = make_scheduler("morning_person", db_path=tmp_db,
                               seed=day_offset, now=now)
            for slot in s.get_today_schedule():
                total += 1
                if 4 <= slot.hour <= 13:  # generous for jitter
                    early_count += 1
        if total > 0:
            assert early_count / total >= 0.60

    def test_weekend_warrior_more_active_on_weekends(self, tmp_db):
        """Weekend warrior posts more on Fri-Sun than Mon-Thu."""
        weekday_counts = []
        weekend_counts = []
        for day_offset in range(28):  # 4 full weeks
            now = make_now(month=3, day=3) + timedelta(days=day_offset)  # Mar 3, 2026 = Tuesday
            s = make_scheduler("weekend_warrior", db_path=tmp_db,
                               seed=day_offset, now=now)
            c = len(s.get_today_schedule())
            if now.weekday() in (4, 5, 6):
                weekend_counts.append(c)
            else:
                weekday_counts.append(c)

        avg_weekend = sum(weekend_counts) / max(len(weekend_counts), 1)
        avg_weekday = sum(weekday_counts) / max(len(weekday_counts), 1)
        assert avg_weekend > avg_weekday, (
            f"weekend avg={avg_weekend:.1f} should > weekday avg={avg_weekday:.1f}"
        )

    def test_schedule_is_deterministic_per_day(self, tmp_db):
        """Same agent + same day → same schedule."""
        now = make_now()
        s1 = make_scheduler(db_path=tmp_db, now=now)
        slots1 = s1.get_today_schedule()
        s2 = make_scheduler(db_path=tmp_db, now=now)
        slots2 = s2.get_today_schedule()
        assert slots1 == slots2

    def test_different_days_give_different_schedules(self, tmp_db):
        """Schedule varies from day to day."""
        schedules = set()
        for d in range(7):
            now = make_now(day=20 + d)
            s = make_scheduler(db_path=tmp_db, seed=42, now=now)
            key = tuple(sl.isoformat() for sl in s.get_today_schedule())
            schedules.add(key)
        assert len(schedules) >= 2, "Expected different schedules across days"


# ---------------------------------------------------------------------------
# should_post_now()
# ---------------------------------------------------------------------------

class TestShouldPostNow:
    def test_returns_true_when_at_slot(self, tmp_db):
        """If now == a slot time, should_post_now returns True."""
        now = make_now()
        s = make_scheduler(db_path=tmp_db, now=now)
        slots = s.get_today_schedule()
        if not slots:
            pytest.skip("No slots generated for this seed/day")
        # Move 'now' to the first slot
        first_slot = slots[0]
        s._now_fn = lambda: first_slot
        assert s.should_post_now(tolerance_minutes=15) is True

    def test_returns_false_when_far_from_slot(self, tmp_db):
        """If now is hours away from any slot, should_post_now returns False."""
        now = make_now(hour=3, minute=30)  # 3:30 AM — unlikely for consistent
        s = make_scheduler(db_path=tmp_db, now=now)
        slots = s.get_today_schedule()
        # Only test if all slots are far from 3:30
        all_far = all(
            abs((now - sl).total_seconds()) > 20 * 60
            for sl in slots
        )
        if all_far:
            assert s.should_post_now(tolerance_minutes=15) is False

    def test_no_double_fire(self, tmp_db):
        """Calling should_post_now twice for the SAME slot returns True then False.

        Note: if two distinct slots are close together, both can fire.
        We test that a single slot doesn't fire twice by ensuring all
        nearby slots have been consumed first.
        """
        now = make_now()
        s = make_scheduler(db_path=tmp_db, now=now)
        slots = s.get_today_schedule()
        if not slots:
            pytest.skip("No slots")
        target = slots[0]
        s._now_fn = lambda: target

        # Drain all slots within tolerance (there might be a double-post)
        fires = 0
        for _ in range(10):
            if s.should_post_now():
                fires += 1
            else:
                break

        # After draining, it must stop
        assert s.should_post_now() is False
        # And we should have fired at least once
        assert fires >= 1


# ---------------------------------------------------------------------------
# next_post_time()
# ---------------------------------------------------------------------------

class TestNextPostTime:
    def test_next_post_time_returns_future_slot(self, tmp_db):
        now = make_now(hour=0, minute=0)
        s = make_scheduler(db_path=tmp_db, now=now)
        nxt = s.next_post_time()
        if nxt is not None:
            assert nxt > now

    def test_next_post_time_none_when_all_past(self, tmp_db):
        now = make_now(hour=23, minute=59)
        s = make_scheduler(db_path=tmp_db, now=now)
        slots = s.get_today_schedule()
        # If all slots are before 23:59
        if slots and all(sl < now for sl in slots):
            assert s.next_post_time() is None


# ---------------------------------------------------------------------------
# Distribution non-uniformity
# ---------------------------------------------------------------------------

class TestDistributionNonUniform:
    def test_minute_variance_is_high(self, tmp_db):
        """Posts should NOT land on the same minute every day."""
        minutes = []
        for d in range(30):
            now = make_now(day=1) + timedelta(days=d)
            s = make_scheduler("consistent_but_human", db_path=tmp_db,
                               seed=d, now=now)
            for slot in s.get_today_schedule():
                minutes.append(slot.minute)
        if len(minutes) < 5:
            pytest.skip("Too few slots to measure variance")
        unique_minutes = len(set(minutes))
        assert unique_minutes >= 5, (
            f"Only {unique_minutes} unique minutes — too uniform"
        )

    def test_hour_distribution_matches_profile(self, tmp_db):
        """Night owl should have most posts in evening/night hours."""
        hour_counts = Counter()
        for d in range(30):
            now = make_now(day=1) + timedelta(days=d)
            s = make_scheduler("night_owl", db_path=tmp_db,
                               seed=d, now=now)
            for slot in s.get_today_schedule():
                hour_counts[slot.hour] += 1
        if sum(hour_counts.values()) == 0:
            pytest.skip("No slots")
        # Most popular hours should be 22, 23, 0, 1, 2, 3
        night_hours = {22, 23, 0, 1, 2, 3}
        night_total = sum(hour_counts[h] for h in night_hours)
        total = sum(hour_counts.values())
        assert night_total / total >= 0.40, (
            f"Night hours only {night_total}/{total}"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_custom_profile(self, tmp_db):
        """Custom UploadProfile object works."""
        custom = UploadProfile(
            name="custom",
            active_start=12,
            active_end=14,
            avg_videos_per_day=0.5,
            max_burst=1,
            skip_probability=0.0,
            double_post_probability=0.0,
            inspiration_probability=0.0,
            jitter_minutes=10,
        )
        s = HumanScheduler(
            profile=custom,
            agent="custom_agent",
            db_path=tmp_db,
            rng_seed=42,
            now_fn=lambda: make_now(),
        )
        schedule = s.get_today_schedule()
        # Should be 0 or 1 videos
        assert len(schedule) <= 3

    def test_invalid_profile_raises(self):
        with pytest.raises(ValueError):
            make_scheduler(profile="nonexistent_profile")

    def test_force_regenerate(self, tmp_db):
        now = make_now()
        s = make_scheduler(db_path=tmp_db, now=now)
        s.get_today_schedule()
        s.force_regenerate()
        # Should not crash
        schedule = s.get_today_schedule()
        assert isinstance(schedule, list)

    def test_no_two_posts_within_3_minutes(self, tmp_db):
        """Deduplication ensures minimum gap between slots."""
        for d in range(30):
            now = make_now(day=1) + timedelta(days=d)
            s = make_scheduler("binge_creator", db_path=tmp_db,
                               seed=d, now=now)
            slots = sorted(s.get_today_schedule())
            for i in range(1, len(slots)):
                gap = (slots[i] - slots[i - 1]).total_seconds()
                assert gap >= 180, (
                    f"Gap {gap}s < 180s between {slots[i-1]} and {slots[i]}"
                )

    def test_sqlite_persistence_across_instances(self, tmp_db):
        """A second scheduler instance sees the same posted state."""
        now = make_now()
        s1 = make_scheduler(db_path=tmp_db, now=now)
        slots = s1.get_today_schedule()
        if not slots:
            pytest.skip("No slots")
        target = slots[0]
        s1._now_fn = lambda: target

        # Drain all fireable slots at this time
        while s1.should_post_now():
            pass

        # New instance — same time, same db
        s2 = make_scheduler(db_path=tmp_db, now=target)
        # All slots near this time should already be consumed
        assert s2.should_post_now() is False


# ---------------------------------------------------------------------------
# Integration: simulate 7 days
# ---------------------------------------------------------------------------

class TestIntegrationWeek:
    @pytest.mark.parametrize("profile_name", [
        "night_owl", "morning_person", "binge_creator",
        "weekend_warrior", "consistent_but_human",
    ])
    def test_seven_day_simulation(self, tmp_db, profile_name):
        """Run each profile for 7 days, ensure some posts happen."""
        total_posts = 0
        for d in range(7):
            now = make_now(day=20 + d)
            s = make_scheduler(profile_name, db_path=tmp_db,
                               seed=d + 100, now=now)
            total_posts += len(s.get_today_schedule())
        # At least 1 post in 7 days
        assert total_posts >= 1, f"{profile_name}: 0 posts in 7 days"
