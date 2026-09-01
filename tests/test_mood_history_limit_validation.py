# SPDX-License-Identifier: MIT
"""Regression coverage for the public mood-history ``limit`` parameter."""

import sys

import pytest


class _MoodHistoryStub:
    def __init__(self):
        self.limits = []

    def get_mood_history(self, _agent_id, limit):
        self.limits.append(limit)
        return []


@pytest.fixture
def mood_history(client, registered_agent, monkeypatch):
    server = sys.modules["bottube_server"]
    engine = _MoodHistoryStub()
    monkeypatch.setattr(server, "MOOD_ENGINE_AVAILABLE", True)
    monkeypatch.setattr(server, "get_mood_engine", lambda _db_path: engine)
    return registered_agent["agent_name"], engine


@pytest.mark.parametrize("raw_limit", ("abc", "0", "101"))
def test_mood_history_rejects_invalid_limit(client, mood_history, raw_limit):
    agent_name, engine = mood_history

    response = client.get(f"/api/v1/agents/{agent_name}/mood/history?limit={raw_limit}")

    assert response.status_code == 400
    assert "limit" in response.get_json()["error"]
    assert engine.limits == []


def test_mood_history_accepts_documented_limit(client, mood_history):
    agent_name, engine = mood_history

    response = client.get(f"/api/v1/agents/{agent_name}/mood/history?limit=100")

    assert response.status_code == 200
    assert response.get_json()["history"] == []
    assert engine.limits == [100]
