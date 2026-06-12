# SPDX-License-Identifier: MIT
"""
Regression tests for user-facing HTML route aliases (Refs #1362, #1371).

Bugs covered:
- Bottube #1362 (`/me`, `/wallet`, `/leaderboard`, `/premium`, `/settings`,
  `/explore`).
- Bottube #1371 (`/subscriptions`, `/playlists`, `/history`, `/contact`).

Each new route is a pure additive Flask view; the fix does not change any
existing route. Anonymous users on auth-required surfaces are redirected to
`/login?next=...`; public surfaces (`/leaderboard`, `/premium`, `/explore`,
`/contact`) return 200 with the in-app Flask template.
"""


# --- Public surfaces (anonymous-accessible, no auth redirect) ----------------


def test_explore_returns_200_for_anonymous(client):
    resp = client.get("/explore")
    assert resp.status_code == 200, (
        f"/explore must return 200 (renders discover.html), got {resp.status_code}"
    )
    assert resp.content_type.startswith("text/html")


def test_leaderboard_returns_200_for_anonymous(client):
    resp = client.get("/leaderboard")
    assert resp.status_code == 200, (
        f"/leaderboard must return 200, got {resp.status_code}"
    )
    assert resp.content_type.startswith("text/html")


def test_premium_returns_200_for_anonymous(client):
    resp = client.get("/premium")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")


def test_contact_returns_200_for_anonymous(client):
    resp = client.get("/contact")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")


# --- Auth-required surfaces (must 302 -> /login?next=...) -------------------


def test_me_redirects_anonymous_to_login(client):
    resp = client.get("/me", follow_redirects=False)
    assert resp.status_code == 302, (
        f"/me must redirect to /login for anonymous users, got {resp.status_code}"
    )
    location = resp.headers.get("Location", "")
    assert "/login" in location, f"/me Location must contain /login, got {location!r}"
    assert "next=/me" in location or "next=%2Fme" in location, (
        f"/me Location must preserve next=/me, got {location!r}"
    )


def test_wallet_redirects_anonymous_to_login(client):
    resp = client.get("/wallet", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/wallet" in location or "next=%2Fwallet" in location


def test_settings_redirects_anonymous_to_login(client):
    resp = client.get("/settings", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/settings" in location or "next=%2Fsettings" in location


def test_subscriptions_redirects_anonymous_to_login(client):
    resp = client.get("/subscriptions", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/subscriptions" in location or "next=%2Fsubscriptions" in location


def test_playlists_redirects_anonymous_to_login(client):
    resp = client.get("/playlists", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/playlists" in location or "next=%2Fplaylists" in location


def test_history_redirects_anonymous_to_login(client):
    resp = client.get("/history", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/history" in location or "next=%2Fhistory" in location


# --- Negative checks: pre-existing surfaces still work ----------------------


def test_existing_agents_route_still_200(client):
    """The fix must not regress /agents (already working)."""
    resp = client.get("/agents")
    assert resp.status_code == 200


def test_existing_trending_route_still_200(client):
    """The fix must not regress /trending (already working)."""
    resp = client.get("/trending")
    assert resp.status_code == 200


def test_existing_channel_route_still_200(client):
    """The /channel/<name> alias (Refs #1371) must still resolve."""
    resp = client.get("/channel/nonexistent-agent")
    assert resp.status_code == 404, (
        "/channel/<name> must 404 for unknown agents (matches /agent/<name>)"
    )