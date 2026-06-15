# SPDX-License-Identifier: MIT
"""
Regression tests for GET /api/feed pagination OFFSET overflow.

Bug: ``page`` was parsed with ``_parse_positive_int_query("page", 1)`` without
an upper bound. Type and sign validation already returned 400 for ``page=abc``
or ``page=-1`` (issue #1456 / PR #1402), but an in-range *positive* integer that
is astronomically large still slipped through. Such a ``?page`` makes
``offset = (page - 1) * per_page`` exceed SQLite's signed 64-bit INTEGER range,
which raises ``OverflowError`` ("Python int too large to convert to SQLite
INTEGER") on the ``LIMIT ? OFFSET ?`` query and surfaces as an HTTP 500.

Verified on production before the fix (unauthenticated):
    GET https://bottube.ai/api/feed?page=9223372036854775807 -> 500
    GET https://bottube.ai/api/feed?page=999999999999999     -> 200  (safe offset)

Fix: bound ``page`` at 10000 (mirroring the existing ``/api/videos`` cap from
issue #1414) so an out-of-range page returns a clean 400 before any offset is
computed, while ordinary pagination is untouched.
"""

_SQLITE_MAX_SIGNED_INT = 2 ** 63 - 1


def test_feed_max_int_page_returns_400_not_500(client):
    """A page at SQLite's 64-bit ceiling must 400 cleanly, never 500."""
    resp = client.get(f"/api/feed?page={_SQLITE_MAX_SIGNED_INT}")
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}"
    assert "page" in resp.get_json()["error"]


def test_feed_overflowing_page_returns_400(client):
    """A page beyond 64 bits (offset overflow) must 400, never 500."""
    resp = client.get("/api/feed?page=99999999999999999999999999")
    assert resp.status_code == 400


def test_feed_v1_alias_overflowing_page_returns_400(client):
    """The /api/v1/feed alias shares the handler and must also 400."""
    resp = client.get(f"/api/v1/feed?page={_SQLITE_MAX_SIGNED_INT}")
    assert resp.status_code == 400


def test_feed_normal_page_still_ok(client):
    """The fix must not regress ordinary pagination."""
    resp = client.get("/api/feed?page=1")
    assert resp.status_code == 200
    assert "videos" in resp.get_json()


def test_feed_page_at_bound_ok(client):
    """The maximum allowed page (10000) is still accepted."""
    resp = client.get("/api/feed?page=10000")
    assert resp.status_code == 200
    assert "videos" in resp.get_json()


def test_feed_page_just_over_bound_returns_400(client):
    """One past the cap is rejected with a clean 400."""
    resp = client.get("/api/feed?page=10001")
    assert resp.status_code == 400
    assert "page" in resp.get_json()["error"]
