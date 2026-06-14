# SPDX-License-Identifier: MIT
"""
Regression tests for Bottube #1431 — Tips leaderboards silently accept
malformed `limit` query parameters.

Before the fix:
    GET /api/tips/leaderboard?limit=abc -> 200 (silently uses default 20)
    GET /api/tips/tippers?limit=abc     -> 200 (silently uses default 20)

After the fix (this PR):
    GET /api/tips/leaderboard?limit=abc -> 400 {"error": "Invalid 'limit' parameter: expected an integer."}
    GET /api/tips/tippers?limit=abc     -> 400 {"error": "Invalid 'limit' parameter: expected an integer."}

Related: Bottube #1411, #1426, #1403 (sibling malformed-pagination fixes),
rustchain-bounties#1102 (claim context).
"""


def test_tips_leaderboard_rejects_malformed_limit(client):
    response = client.get("/api/tips/leaderboard?limit=abc")

    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]
    assert "integer" in data["error"]


def test_tips_tippers_rejects_malformed_limit(client):
    response = client.get("/api/tips/tippers?limit=abc")

    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]
    assert "integer" in data["error"]


def test_tips_leaderboard_rejects_limit_above_max(client):
    response = client.get("/api/tips/leaderboard?limit=999")

    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]
    assert "maximum" in data["error"]


def test_tips_tippers_rejects_limit_below_min(client):
    response = client.get("/api/tips/tippers?limit=0")

    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]
    assert "minimum" in data["error"]


def test_tips_leaderboard_accepts_valid_limit(client):
    # Empty result body is fine; the point is that validation passed.
    response = client.get("/api/tips/leaderboard?limit=5")

    assert response.status_code == 200
    data = response.get_json()
    assert "leaderboard" in data
    assert isinstance(data["leaderboard"], list)


def test_tips_tippers_accepts_valid_limit(client):
    response = client.get("/api/tips/tippers?limit=5")

    assert response.status_code == 200
    data = response.get_json()
    assert "leaderboard" in data
    assert isinstance(data["leaderboard"], list)


def test_tips_leaderboard_defaults_when_limit_omitted(client):
    # No `limit` query parameter at all -> use the documented default of 20.
    response = client.get("/api/tips/leaderboard")

    assert response.status_code == 200
    data = response.get_json()
    assert "leaderboard" in data


def test_tips_tippers_defaults_when_limit_omitted(client):
    response = client.get("/api/tips/tippers")

    assert response.status_code == 200
    data = response.get_json()
    assert "leaderboard" in data
