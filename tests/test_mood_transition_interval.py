# SPDX-License-Identifier: MIT
"""Regression coverage for mood transition timing."""

import mood_engine
from mood_engine import MoodEngine, MoodState


def test_frequent_updates_do_not_postpone_transition_forever(monkeypatch, tmp_path):
    now = [1_000_000.0]
    monkeypatch.setattr(mood_engine.time, "time", lambda: now[0])
    monkeypatch.setattr(mood_engine.random, "random", lambda: 0.0)

    engine = MoodEngine(str(tmp_path / "moods.db"))
    mood = engine.update_mood(1, force_state=MoodState.ENERGETIC)
    assert mood.state is MoodState.ENERGETIC

    # A normal scheduler may call update_mood every ten minutes. Those calls
    # should update intensity, but must not restart the one-hour state timer.
    for interval in range(1, 6):
        now[0] = 1_000_000.0 + interval * 600
        mood = engine.update_mood(1)
        assert mood.state is MoodState.ENERGETIC

    now[0] = 1_000_000.0 + engine.MIN_MOOD_DURATION
    mood = engine.update_mood(1)

    assert mood.state is MoodState.EXCITED
    assert mood.started_at == now[0]
