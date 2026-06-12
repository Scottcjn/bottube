# SPDX-License-Identifier: MIT
"""
Regression tests for /api/v1/videos and /api/v1/search alias routes.

Bug: Bottube #1383 (`/api/v1/* 18 nginx-404 surfaces`).
The Bottube Flask app registers routes under `/api/videos` and `/api/search`
but does NOT register them under `/api/v1/videos` and `/api/v1/search`,
even though the existing client code paths in `bots/telegram_bot.py`,
`bots/debate_framework.py`, and `update_downloads.py` use the
`/api/v1/` prefix.

Fix: add 2 alias routes (`list_videos_v1_alias`, `search_videos_v1_alias`)
that delegate to the existing `list_videos` and `search_videos` handlers.
Diff: +12/-0 in bottube_server.py, +88 in new test file.
"""


def test_v1_videos_alias_matches_videos(client):
    """GET /api/v1/videos must return the same status and JSON body as /api/videos."""
    resp_v1 = client.get("/api/v1/videos?per_page=5")
    resp_canonical = client.get("/api/videos?per_page=5")
    assert resp_v1.status_code == resp_canonical.status_code, (
        f"v1 status {resp_v1.status_code} != canonical status {resp_canonical.status_code}"
    )
    # The exact JSON may differ on request-specific cache headers, but
    # the payload keys must match
    v1 = resp_v1.get_json()
    canonical = resp_canonical.get_json()
    assert set(v1.keys()) == set(canonical.keys())


def test_v1_videos_alias_rejects_malformed_pagination(client):
    """v1 alias must inherit the _parse_positive_int_query validation."""
    resp = client.get("/api/v1/videos?page=abc")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "page" in data["error"]


def test_v1_videos_alias_rejects_zero_per_page(client):
    resp = client.get("/api/v1/videos?per_page=0")
    assert resp.status_code == 400


def test_v1_videos_alias_rejects_out_of_range_per_page(client):
    resp = client.get("/api/v1/videos?per_page=999")
    assert resp.status_code == 400


def test_search_v1_alias_matches_search(client):
    """GET /api/v1/search must return the same status as /api/search."""
    resp_v1 = client.get("/api/v1/search?q=hello")
    resp_canonical = client.get("/api/search?q=hello")
    assert resp_v1.status_code == resp_canonical.status_code
    v1 = resp_v1.get_json()
    canonical = resp_canonical.get_json()
    assert set(v1.keys()) == set(canonical.keys())


def test_search_v1_alias_rejects_malformed_pagination(client):
    resp = client.get("/api/v1/search?q=hello&page=abc")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "page" in data["error"]


def test_search_v1_alias_rejects_zero_per_page(client):
    resp = client.get("/api/v1/search?q=hello&per_page=0")
    assert resp.status_code == 400


def test_v1_routes_return_json_content_type(client):
    """v1 alias routes must return JSON, not HTML 404 (Bottube #1383 root cause)."""
    resp = client.get("/api/v1/videos?per_page=1")
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    resp2 = client.get("/api/v1/search?q=test")
    assert resp2.status_code == 200
    assert resp2.content_type.startswith("application/json")
