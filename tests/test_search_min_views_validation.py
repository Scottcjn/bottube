# SPDX-License-Identifier: MIT
"""
Regression tests for Bottube #1425 — `/api/search` silently ignores
malformed `min_views` query parameter.

Bug: `/api/search?q=retro&min_views=abc` returns HTTP 200 with the
engagement threshold silently disabled (Flask's `type=int` falls back
to the default 0 on parse failure). This hides client bugs and is
inconsistent with the already-hardened `/api/search` pagination
parameters.

Fix: route `min_views` through the existing `_parse_positive_int_query`
helper that `page` and `per_page` already use, so malformed values
return `400 {"error": "min_views must be an integer"}` like the other
parameters.

Refs: https://github.com/Scottcjn/bottube/issues/1425
"""


def test_search_min_views_rejects_malformed_string(client):
    """GET /api/search?min_views=abc must return 400 (was 200 silently)."""
    resp = client.get("/api/search?q=retro&min_views=abc")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "min_views" in data["error"]
    assert "integer" in data["error"]


def test_search_min_views_rejects_malformed_negative(client):
    """GET /api/search?min_views=-5 must return 400 (min_value=0 enforced)."""
    resp = client.get("/api/search?q=retro&min_views=-5")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "min_views" in data["error"]


def test_search_min_views_accepts_zero(client):
    """GET /api/search?min_views=0 is a valid no-op filter, must return 200."""
    resp = client.get("/api/search?q=retro&min_views=0")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["filters"]["min_views"] is None


def test_search_min_views_accepts_positive(client):
    """GET /api/search?min_views=10 must return 200 with the threshold echoed."""
    resp = client.get("/api/search?q=retro&min_views=10")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["filters"]["min_views"] == 10


def test_search_min_views_omitted_default(client):
    """GET /api/search?q=retro (no min_views) must return 200 with null filter."""
    resp = client.get("/api/search?q=retro")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["filters"]["min_views"] is None
