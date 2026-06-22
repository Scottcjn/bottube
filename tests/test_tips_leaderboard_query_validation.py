# SPDX-License-Identifier: MIT
"""Regression tests for issue #1431.

The public tips leaderboard endpoints silently coerced a malformed ``limit``
query parameter to the default size (HTTP 200), which made malformed requests
indistinguishable from valid default ones and was inconsistent with the rest of
the public query-validation surface (e.g. ``/api/quests/leaderboard``).

They now reject a non-integer ``limit`` with a deterministic JSON 400 while
still clamping valid values into the supported range.
"""


def test_tips_leaderboard_rejects_malformed_limit(client):
    response = client.get("/api/tips/leaderboard?limit=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "limit must be an integer"}


def test_tips_tippers_rejects_malformed_limit(client):
    response = client.get("/api/tips/tippers?limit=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "limit must be an integer"}


def test_tips_leaderboard_accepts_valid_limit(client):
    response = client.get("/api/tips/leaderboard?limit=5")

    assert response.status_code == 200
    assert "leaderboard" in response.get_json()


def test_tips_tippers_accepts_valid_limit(client):
    response = client.get("/api/tips/tippers?limit=5")

    assert response.status_code == 200
    assert "leaderboard" in response.get_json()


def test_tips_leaderboard_default_limit_still_works(client):
    response = client.get("/api/tips/leaderboard")

    assert response.status_code == 200
    assert "leaderboard" in response.get_json()
