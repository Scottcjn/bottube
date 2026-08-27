# SPDX-License-Identifier: MIT


def test_quests_leaderboard_rejects_malformed_limit(client):
    """Verify the quests leaderboard rejects a non-integer limit query param.

    The leaderboard endpoint accepts `limit` to cap the number of rows
    returned. A non-integer value (e.g. `limit=abc`) must be rejected with
    a 400 and a clear error so clients can fix their request instead of
    getting a 500 from a downstream SQL or Python coercion.
    """
    response = client.get("/api/quests/leaderboard?limit=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "limit must be an integer"}


def test_gamification_leaderboard_rejects_malformed_limit(client):
    """Verify the gamification leaderboard rejects a non-integer limit.

    Mirrors the quests leaderboard validation: malformed `limit` query
    parameters must surface as 400s with the same canonical error message
    so client SDKs can handle both leaderboards with one error path.
    """
    response = client.get("/api/gamification/leaderboard?limit=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "limit must be an integer"}

