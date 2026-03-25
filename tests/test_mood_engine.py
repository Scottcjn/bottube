# SPDX-License-Identifier: MIT
"""Tests for mood_engine.py — Agent Mood System."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mood_engine import (
    MOOD_META,
    Mood,
    MoodEngine,
    MoodSignals,
    MoodState,
)


@pytest.fixture
def engine(tmp_path):
    return MoodEngine(
        agent="test_bot",
        db_path=tmp_path / "mood.db",
        transition_cooldown=0,
        rng_seed=42,
        now_fn=lambda: 1700000000.0,
    )


class TestMoodDefinitions:
    def test_all_moods_have_meta(self):
        for m in Mood:
            assert m in MOOD_META
            meta = MOOD_META[m]
            assert "emoji" in meta
            assert "color" in meta
            assert "title_prefixes" in meta
            assert "exclamation_rate" in meta

    def test_seven_moods(self):
        assert len(Mood) == 7


class TestMoodState:
    def test_to_dict(self):
        state = MoodState(
            mood=Mood.EXCITED, intensity=0.75,
            since=1000.0, trigger="test", emoji="🎉",
        )
        d = state.to_dict()
        assert d["mood"] == "excited"
        assert d["intensity"] == 0.75


class TestMoodTransitions:
    def test_default_mood_is_contemplative(self, engine):
        assert engine.current().mood == Mood.CONTEMPLATIVE

    def test_low_views_causes_frustration(self, engine):
        state = engine.update(low_view_streak=3, views_recent=5, views_average=50)
        assert state.mood == Mood.FRUSTRATED
        assert state.trigger == "low_views_streak"

    def test_viral_video_causes_excitement(self, engine):
        state = engine.update(views_recent=300, views_average=50)
        assert state.mood == Mood.EXCITED
        assert state.trigger == "viral_video"

    def test_negative_comments_cause_frustration(self, engine):
        state = engine.update(
            comments_positive=1, comments_negative=5, comments_total=6,
        )
        assert state.mood == Mood.FRUSTRATED
        assert state.trigger == "negative_comments"

    def test_positive_engagement_causes_excitement(self, engine):
        state = engine.update(
            comments_positive=10, comments_negative=1, comments_total=11,
        )
        assert state.mood == Mood.EXCITED
        assert state.trigger == "positive_engagement"

    def test_late_night_causes_tiredness(self, engine):
        state = engine.update(hour=2)
        assert state.mood == Mood.TIRED
        assert state.trigger == "late_night"

    def test_morning_causes_energy(self, engine):
        state = engine.update(hour=8)
        assert state.mood == Mood.ENERGETIC
        assert state.trigger == "morning"

    def test_evening_causes_contemplation(self, engine):
        engine.force_mood("energetic")
        state = engine.update(hour=20)
        assert state.mood == Mood.CONTEMPLATIVE

    def test_weekend_causes_playfulness(self, engine):
        state = engine.update(day_of_week=5, hour=14)
        assert state.mood == Mood.PLAYFUL

    def test_upload_burnout(self, engine):
        state = engine.update(videos_last_24h=5, hour=14)
        assert state.mood == Mood.TIRED
        assert state.trigger == "upload_burnout"

    def test_milestone_causes_nostalgia(self, engine):
        state = engine.update(total_videos=100, hour=14)
        assert state.mood == Mood.NOSTALGIC
        assert state.trigger == "milestone"

    def test_frustration_intensifies_with_longer_streak(self, engine):
        state = engine.update(low_view_streak=5)
        assert state.intensity > 0.5


class TestCooldown:
    def test_cooldown_prevents_rapid_transition(self, tmp_path):
        t = [1000.0]
        engine = MoodEngine(
            agent="test",
            db_path=tmp_path / "mood.db",
            transition_cooldown=3600,
            rng_seed=42,
            now_fn=lambda: t[0],
        )
        # First transition
        engine.update(low_view_streak=3)
        assert engine.current().mood == Mood.FRUSTRATED

        # Try to transition immediately → blocked by cooldown
        t[0] = 1000.0 + 100  # only 100s later
        engine.update(views_recent=300, views_average=50)
        assert engine.current().mood == Mood.FRUSTRATED  # didn't change

    def test_transition_after_cooldown_expires(self, tmp_path):
        t = [1000.0]
        engine = MoodEngine(
            agent="test",
            db_path=tmp_path / "mood.db",
            transition_cooldown=3600,
            rng_seed=42,
            now_fn=lambda: t[0],
        )
        engine.update(low_view_streak=3)
        assert engine.current().mood == Mood.FRUSTRATED

        t[0] = 1000.0 + 4000  # 4000s > 3600s cooldown
        engine.update(views_recent=300, views_average=50)
        assert engine.current().mood == Mood.EXCITED


class TestGetStyle:
    def test_style_has_required_fields(self, engine):
        style = engine.get_style()
        assert "mood" in style
        assert "emoji" in style
        assert "color" in style
        assert "title_prefix" in style
        assert "title_suffix" in style
        assert "exclamation_rate" in style
        assert "upload_frequency_multiplier" in style

    def test_frustrated_style(self, engine):
        engine.force_mood("frustrated")
        style = engine.get_style()
        assert style["exclamation_rate"] < 0.3
        assert style["upload_frequency_multiplier"] < 1.0

    def test_energetic_style(self, engine):
        engine.force_mood("energetic")
        style = engine.get_style()
        assert style["exclamation_rate"] > 0.3
        assert style["upload_frequency_multiplier"] > 1.0


class TestPersistence:
    def test_state_survives_reload(self, tmp_path):
        db = tmp_path / "mood.db"
        e1 = MoodEngine(agent="bot", db_path=db, transition_cooldown=0,
                         rng_seed=42, now_fn=lambda: 1000.0)
        e1.update(low_view_streak=4)
        assert e1.current().mood == Mood.FRUSTRATED

        # New instance, same DB
        e2 = MoodEngine(agent="bot", db_path=db, transition_cooldown=0,
                         rng_seed=42, now_fn=lambda: 1000.0)
        assert e2.current().mood == Mood.FRUSTRATED

    def test_history_recorded(self, engine):
        engine.update(low_view_streak=3)
        engine.force_mood("excited", trigger="test_force")
        history = engine.get_history()
        assert len(history) >= 2
        moods = [h["mood"] for h in history]
        assert "excited" in moods


class TestForceMood:
    def test_force_mood_by_string(self, engine):
        engine.force_mood("playful")
        assert engine.current().mood == Mood.PLAYFUL

    def test_force_mood_by_enum(self, engine):
        engine.force_mood(Mood.NOSTALGIC)
        assert engine.current().mood == Mood.NOSTALGIC

    def test_invalid_mood_raises(self, engine):
        with pytest.raises(ValueError):
            engine.force_mood("nonexistent")


class TestExampleScenario:
    def test_agent_journey(self, tmp_path):
        """Simulate: 3 bad videos → frustrated → then viral → excited."""
        t = [1000.0]
        engine = MoodEngine(
            agent="cosmo",
            db_path=tmp_path / "mood.db",
            transition_cooldown=0,
            rng_seed=42,
            now_fn=lambda: t[0],
        )

        # Starts contemplative
        assert engine.current().mood == Mood.CONTEMPLATIVE

        # 3 videos with <10 views while average is 50
        t[0] += 100
        state = engine.update(
            low_view_streak=3, views_recent=8, views_average=50, hour=14,
        )
        assert state.mood == Mood.FRUSTRATED

        # Then one video gets 200 views (4x average)
        t[0] += 100
        state = engine.update(
            views_recent=200, views_average=50, low_view_streak=0, hour=14,
        )
        assert state.mood == Mood.EXCITED

        # Check history
        history = engine.get_history()
        assert len(history) >= 2
