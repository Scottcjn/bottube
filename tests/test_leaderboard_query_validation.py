# SPDX-License-Identifier: MIT


def test_quests_leaderboard_rejects_malformed_limit(client):
    response = client.get("/api/quests/leaderboard?limit=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "limit must be an integer"}


def test_gamification_leaderboard_rejects_malformed_limit(client):
    response = client.get("/api/gamification/leaderboard?limit=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "limit must be an integer"}

