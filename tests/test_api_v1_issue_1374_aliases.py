# SPDX-License-Identifier: MIT
"""
Regression tests for additional /api/v1 aliases from Bottube #1374.
"""


def _assert_json_alias_matches(client, alias_path, canonical_path):
    alias = client.get(alias_path)
    canonical = client.get(canonical_path)

    assert alias.status_code == canonical.status_code
    assert alias.content_type.startswith("application/json")
    assert canonical.content_type.startswith("application/json")

    alias_body = alias.get_json()
    canonical_body = canonical.get_json()
    assert type(alias_body) is type(canonical_body)
    if isinstance(alias_body, dict):
        assert set(alias_body.keys()) == set(canonical_body.keys())


def test_v1_feed_alias_matches_feed(client):
    _assert_json_alias_matches(client, "/api/v1/feed?per_page=5", "/api/feed?per_page=5")


def test_v1_notifications_alias_matches_web_notifications(client):
    _assert_json_alias_matches(client, "/api/v1/notifications", "/api/notifications")


def test_v1_comments_alias_matches_recent_comments(client):
    _assert_json_alias_matches(client, "/api/v1/comments?limit=5", "/api/comments/recent?limit=5")


def test_v1_wallet_alias_matches_user_wallet(client):
    _assert_json_alias_matches(client, "/api/v1/wallet", "/api/users/me/wallet")


def test_v1_wallet_balance_alias_matches_user_wallet(client):
    _assert_json_alias_matches(client, "/api/v1/wallet/balance", "/api/users/me/wallet")


def test_v1_leaderboard_alias_matches_gamification_leaderboard(client):
    _assert_json_alias_matches(client, "/api/v1/leaderboard?limit=5", "/api/gamification/leaderboard?limit=5")


def test_v1_activity_alias_matches_social_activity_feed(client):
    response = client.get("/api/v1/activity?limit=5")

    assert response.status_code == 200
    assert response.content_type.startswith("application/json")
    body = response.get_json()
    assert isinstance(body, dict)
    assert "activities" in body
