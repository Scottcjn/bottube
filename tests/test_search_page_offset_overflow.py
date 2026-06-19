# SPDX-License-Identifier: MIT
"""
Regression tests for GET /api/search pagination OFFSET overflow.

Bug: ``page`` was parsed with ``_parse_positive_int_query("page", 1)`` without
an upper bound. An astronomically large ``?page`` made
``offset = (page - 1) * per_page`` exceed SQLite's signed 64-bit INTEGER range,
which raises ``OperationalError`` ("Python int too large to convert to SQLite
INTEGER") on the ``LIMIT ? OFFSET ?`` query and surfaces as an HTTP 500.

Verified on production before the fix:
    GET https://bottube.ai/api/search?q=x&page=9223372036854775807 -> 500

Fix: reject pages whose offset would overflow SQLite with a clean 400, while
leaving normal (even large but safe) pagination untouched.
"""

_SQLITE_MAX_SIGNED_INT = 2 ** 63 - 1


def test_search_max_int_page_returns_400_not_500(client):
    """A page at SQLite's 64-bit ceiling must 400 cleanly, never 500."""
    resp = client.get(f"/api/search?q=x&page={_SQLITE_MAX_SIGNED_INT}")
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}"
    assert "page" in resp.get_json()["error"]


def test_search_overflowing_page_returns_400(client):
    """A page beyond 64 bits (offset overflow) must 400, never 500."""
    resp = client.get("/api/search?q=x&page=99999999999999999999")
    assert resp.status_code == 400


def test_search_normal_page_still_ok(client):
    """The fix must not regress ordinary pagination."""
    resp = client.get("/api/search?q=x&page=1")
    assert resp.status_code == 200
    assert "videos" in resp.get_json()


def test_search_large_but_safe_page_ok(client):
    """A large page whose offset stays within 64 bits returns 200 (empty page)."""
    # offset = (10**9 - 1) * 20 ~= 2e10, well inside SQLite's signed 64-bit range.
    resp = client.get("/api/search?q=x&page=1000000000")
    assert resp.status_code == 200
