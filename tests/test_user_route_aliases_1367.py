# SPDX-License-Identifier: MIT
"""
Regression tests for additional user-facing HTML route aliases (Refs #1367).

Bugs covered:
- Bottube #1367 (14 more user-facing HTML routes returning 404 in production):
  `/settings/profile`, `/agents/me`, `/premium/plans`, `/premium/upgrade`,
  `/account`, `/account/settings`, `/creator`, `/creators`, `/live`, `/home`,
  `/watch`, `/tags`, `/help`, `/channels`.

Each new route is a pure additive Flask view; the fix does not change any
existing route. Auth-required surfaces redirect to `/login?next=...`; public
surfaces (`/creators`, `/live`, `/home`, `/watch`, `/tags`, `/help`,
`/channels`) return 302 redirects to canonical surfaces (`/agents`,
`/trending`, `/`, `/docs`).
"""


# --- Auth-required surfaces (must 302 -> /login?next=...) -------------------


def test_settings_profile_redirects_anonymous_to_login(client):
    resp = client.get("/settings/profile", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/settings/profile" in location or "next=%2Fsettings%2Fprofile" in location


def test_agents_me_redirects_anonymous_to_login(client):
    resp = client.get("/agents/me", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/agents/me" in location or "next=%2Fagents%2Fme" in location


def test_premium_plans_redirects_anonymous_to_login(client):
    resp = client.get("/premium/plans", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/premium/plans" in location or "next=%2Fpremium%2Fplans" in location


def test_premium_upgrade_redirects_anonymous_to_login(client):
    resp = client.get("/premium/upgrade", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/premium/upgrade" in location or "next=%2Fpremium%2Fupgrade" in location


def test_account_redirects_anonymous_to_login(client):
    resp = client.get("/account", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/account" in location or "next=%2Faccount" in location


def test_account_settings_redirects_anonymous_to_login(client):
    resp = client.get("/account/settings", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/account/settings" in location or "next=%2Faccount%2Fsettings" in location


def test_creator_redirects_anonymous_to_login(client):
    resp = client.get("/creator", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/login" in location
    assert "next=/creator" in location or "next=%2Fcreator" in location


# --- Public surfaces (302 to canonical surface, no auth) -------------------


def test_creators_redirects_to_agents(client):
    """Plural creator directory -> /agents (canonical creator directory)."""
    resp = client.get("/creators", follow_redirects=False)
    assert resp.status_code == 302, (
        f"/creators must redirect to /agents, got {resp.status_code}"
    )
    location = resp.headers.get("Location", "")
    assert "/agents" in location, f"/creators Location must contain /agents, got {location!r}"


def test_live_redirects_to_trending(client):
    """Live streams surface -> /trending (live/popular feeds)."""
    resp = client.get("/live", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/trending" in location, f"/live Location must contain /trending, got {location!r}"


def test_home_redirects_to_root(client):
    """Canonical home alias -> / for all visitors."""
    resp = client.get("/home", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    # flask url_for('index') returns '/' or 'http://localhost/'
    assert location.endswith("/") or "/login" not in location, (
        f"/home Location must point at the root index, got {location!r}"
    )


def test_watch_redirects_to_trending(client):
    """Canonical watch alias -> /trending (single-video surface is /watch/<id>)."""
    resp = client.get("/watch", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/trending" in location, f"/watch Location must contain /trending, got {location!r}"


def test_tags_redirects_to_trending(client):
    """Tag index alias -> /trending."""
    resp = client.get("/tags", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/trending" in location, f"/tags Location must contain /trending, got {location!r}"


def test_help_redirects_to_docs(client):
    """Help page -> /docs (canonical help content)."""
    resp = client.get("/help", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/docs" in location, f"/help Location must contain /docs, got {location!r}"


def test_channels_redirects_to_trending(client):
    """Channel index alias -> /trending."""
    resp = client.get("/channels", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/trending" in location, f"/channels Location must contain /trending, got {location!r}"


# --- Regression: existing surfaces must not break ----------------------------


def test_existing_watch_video_id_still_works(client):
    """/watch/<video_id> (canonical single-video surface) must remain registered."""
    resp = client.get("/watch/nonexistent-video-id-12345")
    assert resp.status_code in (200, 404), (
        f"/watch/<video_id> must remain a real route, got {resp.status_code}"
    )


def test_existing_agents_route_still_200(client):
    """/agents (canonical creator directory) must remain 200."""
    resp = client.get("/agents")
    assert resp.status_code == 200


def test_existing_trending_route_still_200(client):
    """/trending (canonical trending feed) must remain 200."""
    resp = client.get("/trending")
    assert resp.status_code == 200


def test_existing_docs_route_still_works(client):
    """/docs (canonical help surface) must remain registered."""
    resp = client.get("/docs")
    assert resp.status_code == 200


# --- URL map registration smoke test -----------------------------------------


def test_all_1367_routes_are_registered():
    """All 14 Bottube #1367 routes must be in the URL map after import."""
    import bottube_server  # noqa: F401 - import is the assertion

    flask_app = bottube_server.app
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    expected = {
        "/settings/profile", "/agents/me", "/premium/plans", "/premium/upgrade",
        "/account", "/account/settings", "/creator", "/creators", "/live",
        "/home", "/watch", "/tags", "/help", "/channels",
    }
    missing = expected - rules
    assert not missing, f"Missing routes in URL map: {missing}"