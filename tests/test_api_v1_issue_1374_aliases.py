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
    """Verify /api/v1/feed returns the same JSON as /api/feed.

    Regression test for #1374: legacy /api/v1/* clients must continue to
    receive the exact same JSON payload as the canonical /api/* routes.
    The helper asserts status code, content-type, body type, and dict
    key set equality so the alias cannot silently diverge (extra keys,
    missing keys, or different types) without breaking this test.
    """
    _assert_json_alias_matches(client, "/api/v1/feed?per_page=5", "/api/feed?per_page=5")


def test_v1_notifications_alias_matches_web_notifications(client):
    """Verify /api/v1/notifications mirrors /api/notifications.

    Same alias-equivalence contract as test_v1_feed_alias_matches_feed
    but for the notifications endpoint. Pinning both routes ensures the
    /v1 namespace stays a thin shim over the canonical route rather
    than a divergent implementation.
    """
    _assert_json_alias_matches(client, "/api/v1/notifications", "/api/notifications")


def test_v1_comments_alias_matches_recent_comments(client):
    """Verify /api/v1/comments mirrors /api/comments/recent.

    /api/v1/comments was the original comments endpoint, renamed to
    /api/comments/recent for clarity (the recent comments feed). The
    alias must keep returning the same JSON shape so /v1 SDKs do not
    need to know about the rename.
    """
    _assert_json_alias_matches(client, "/api/v1/comments?limit=5", "/api/comments/recent?limit=5")


def test_v1_wallet_alias_matches_user_wallet(client):
    """Verify /api/v1/wallet mirrors /api/users/me/wallet.

    Alias contract for the wallet endpoint. The /v1 path is shorter
    and used by mobile SDKs that pre-date the /users/me/* restructure.
    """
    _assert_json_alias_matches(client, "/api/v1/wallet", "/api/users/me/wallet")


def test_v1_wallet_balance_alias_matches_user_wallet(client):
    """Verify /api/v1/wallet/balance mirrors /api/users/me/wallet.

    Alias contract for the wallet-balance subpath. Returns the same
    payload as the full /v1/wallet alias (the balance subpath is just
    a convenience URL for clients that only need the balance number).
    """
    _assert_json_alias_matches(client, "/api/v1/wallet/balance", "/api/users/me/wallet")


def test_v1_leaderboard_alias_matches_gamification_leaderboard(client):
    """Verify /api/v1/leaderboard mirrors /api/gamification/leaderboard.

    The /v1 alias predates the gamification module rename; the
    endpoint still works for old SDKs and must return identical JSON.
    """
    _assert_json_alias_matches(client, "/api/v1/leaderboard?limit=5", "/api/gamification/leaderboard?limit=5")


def test_v1_activity_alias_matches_social_activity_feed(client):
    """Verify /api/v1/activity returns a JSON object with an activities key.

    The activity endpoint has no exact canonical counterpart (the
    /api/v1/* namespace is its own route), so this test asserts the
    minimum viable contract: 200, JSON content-type, top-level dict,
    and an 'activities' array. Future additions to the response shape
    should not break this test as long as the activities key stays.
    """
    response = client.get("/api/v1/activity?limit=5")

    assert response.status_code == 200
    assert response.content_type.startswith("application/json")
    body = response.get_json()
    assert isinstance(body, dict)
    assert "activities" in body
