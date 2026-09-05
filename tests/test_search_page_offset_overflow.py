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
    """A page at SQLite's 64-bit ceiling must 400 cleanly, never 500.

    Regression: a page value equal to 2**63 - 1 produces
    offset = (2**63 - 2) * per_page which overflows SQLite's signed
    INTEGER and previously surfaced as a 500. The fix must detect this
    case and respond 400 with an error message mentioning 'page' so the
    client can show a meaningful validation error.
    """
    resp = client.get(f"/api/search?q=x&page={_SQLITE_MAX_SIGNED_INT}")
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}"
    assert "page" in resp.get_json()["error"]


def test_search_overflowing_page_returns_400(client):
    """A page beyond 64 bits (offset overflow) must 400, never 500.

    Same regression as the previous test but with a value clearly above
    the 64-bit ceiling (20 nines). The overflow check must use a strict
    greater-than against the SQLite max, not just a Python int conversion
    that would raise 500 before the validator runs.
    """
    resp = client.get("/api/search?q=x&page=99999999999999999999")
    assert resp.status_code == 400


def test_search_normal_page_still_ok(client):
    """The fix must not regress ordinary pagination.

    Sanity check: page=1 is the most common case and must continue to
    return 200 with a `videos` key in the body. If the overflow fix
    accidentally tightened the lower bound, this would start returning
    400 for the default request.
    """
    resp = client.get("/api/search?q=x&page=1")
    assert resp.status_code == 200
    assert "videos" in resp.get_json()


def test_search_large_but_safe_page_ok(client):
    """A large page whose offset stays within 64 bits returns 200 (empty page).

    Boundary check for the overflow guard: page=10**9 yields
    offset ~= 2*10**10 which is well inside SQLite's 64-bit range, so
    the endpoint must return 200 (with an empty videos list because
    there is no row that far in). This proves the validator accepts
    'large but valid' inputs and only rejects the overflow range.
    """
    # offset = (10**9 - 1) * 20 ~= 2e10, well inside SQLite's signed 64-bit range.
    resp = client.get("/api/search?q=x&page=1000000000")
    assert resp.status_code == 200
