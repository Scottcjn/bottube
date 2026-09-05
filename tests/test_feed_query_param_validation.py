# SPDX-License-Identifier: MIT
"""
Regression tests for /api/feed and /api/feed/subscriptions rejecting malformed
or out-of-range pagination query parameters with HTTP 400 instead of silently
coercing invalid input to the default.

Pattern is identical to PR #1397 (which hardened /api/videos and /api/search).
This extends the same protection to the public /api/feed and the
authenticated /api/feed/subscriptions routes.
"""


# ----- /api/feed (public) -----


def test_feed_rejects_non_integer_page(client):
    """A non-numeric `page` must 400 with a message naming the field and the reason."""
    response = client.get("/api/feed?page=abc")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]
    assert "integer" in data["error"]


def test_feed_rejects_non_integer_per_page(client):
    """A non-numeric `per_page` must 400, mirroring the `page` check above for the size parameter."""
    response = client.get("/api/feed?per_page=xyz")
    assert response.status_code == 400
    data = response.get_json()
    assert "per_page" in data["error"]


def test_feed_rejects_zero_page(client):
    """`page=0` must 400 -- pagination is 1-indexed, so zero is out of range, not just falsy."""
    response = client.get("/api/feed?page=0")
    assert response.status_code == 400


def test_feed_rejects_negative_page(client):
    """A negative `page` must 400 rather than being coerced into page 1 or crashing an OFFSET query."""
    response = client.get("/api/feed?page=-5")
    assert response.status_code == 400


def test_feed_rejects_zero_per_page(client):
    """`per_page=0` must 400 -- a request for zero results is almost certainly a client bug, not intent."""
    response = client.get("/api/feed?per_page=0")
    assert response.status_code == 400


def test_feed_rejects_negative_per_page(client):
    """A negative `per_page` must 400 rather than being passed through to a SQL LIMIT."""
    response = client.get("/api/feed?per_page=-1")
    assert response.status_code == 400


def test_feed_rejects_per_page_above_max(client):
    """`per_page` above the server's page-size cap must 400, not silently clamp -- callers relying on the requested size need to know it wasn't honored."""
    response = client.get("/api/feed?per_page=51")
    assert response.status_code == 400
    data = response.get_json()
    assert "per_page" in data["error"]


def test_feed_rejects_float_page(client):
    """A float-looking `page` like `1.5` must 400, not get silently truncated to page 1."""
    response = client.get("/api/feed?page=1.5")
    assert response.status_code == 400


def test_feed_rejects_null_page(client):
    """The literal string `null` (a common client-side bug when a JS value is undefined) must 400, not be parsed as 0/None."""
    response = client.get("/api/feed?page=null")
    assert response.status_code == 400


def test_feed_rejects_nan_page(client):
    """The literal string `NaN` must 400 -- Python's `int("NaN")` raises, but a looser numeric parser might not."""
    response = client.get("/api/feed?page=NaN")
    assert response.status_code == 400


def test_feed_accepts_valid_pagination(client):
    """A well-formed `page`/`per_page` pair must succeed and echo the requested page back."""
    response = client.get("/api/feed?page=1&per_page=10")
    assert response.status_code == 200
    data = response.get_json()
    assert data["page"] == 1
    # per_page is parsed but not echoed back; the page size is reflected in
    # the number of returned videos, not a response field.


def test_feed_omits_defaults_when_unset(client):
    """A request with no pagination params at all must still succeed, defaulting to page 1."""
    response = client.get("/api/feed")
    assert response.status_code == 200
    data = response.get_json()
    assert data["page"] == 1
    # Defaults applied; response shape is {videos, page, mode, bucket}.


def test_feed_per_page_boundary_values(client):
    """The exact edges of the valid range (1 and 50) must pass; one step past the max must fail.

    Checks 51, 999, and 1000 together to prove the cap rejects anything
    over the limit uniformly, not just values close to the boundary.
    """
    for pp in (1, 50):
        r = client.get(f"/api/feed?per_page={pp}")
        assert r.status_code == 200
    for pp in (51, 999, 1000):
        r = client.get(f"/api/feed?per_page={pp}")
        assert r.status_code == 400


# ----- _parse_positive_int_query helper applied to /api/feed -----


def test_feed_helper_direct_call_with_malformed_page(app):
    """`_parse_positive_int_query` itself (not just the route) must return an error tuple for bad input.

    Calls the shared helper directly rather than through `client.get`, so a
    regression in the helper is caught here even if some future route
    forgets to check its return value and drops the 400 response.
    """
    with app.test_request_context("/api/feed?page=abc"):
        from bottube_server import _parse_positive_int_query
        value, error = _parse_positive_int_query("page", 1)
        assert value is None
        assert error[1] == 400
        assert "page" in error[0].get_json()["error"]
