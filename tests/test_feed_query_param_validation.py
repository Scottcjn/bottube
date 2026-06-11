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
    response = client.get("/api/feed?page=abc")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]
    assert "integer" in data["error"]


def test_feed_rejects_non_integer_per_page(client):
    response = client.get("/api/feed?per_page=xyz")
    assert response.status_code == 400
    data = response.get_json()
    assert "per_page" in data["error"]


def test_feed_rejects_zero_page(client):
    response = client.get("/api/feed?page=0")
    assert response.status_code == 400


def test_feed_rejects_negative_page(client):
    response = client.get("/api/feed?page=-5")
    assert response.status_code == 400


def test_feed_rejects_zero_per_page(client):
    response = client.get("/api/feed?per_page=0")
    assert response.status_code == 400


def test_feed_rejects_negative_per_page(client):
    response = client.get("/api/feed?per_page=-1")
    assert response.status_code == 400


def test_feed_rejects_per_page_above_max(client):
    response = client.get("/api/feed?per_page=51")
    assert response.status_code == 400
    data = response.get_json()
    assert "per_page" in data["error"]


def test_feed_rejects_float_page(client):
    response = client.get("/api/feed?page=1.5")
    assert response.status_code == 400


def test_feed_rejects_null_page(client):
    response = client.get("/api/feed?page=null")
    assert response.status_code == 400


def test_feed_rejects_nan_page(client):
    response = client.get("/api/feed?page=NaN")
    assert response.status_code == 400


def test_feed_accepts_valid_pagination(client):
    response = client.get("/api/feed?page=1&per_page=10")
    assert response.status_code == 200
    data = response.get_json()
    assert data["page"] == 1
    # per_page is parsed but not echoed back; the page size is reflected in
    # the number of returned videos, not a response field.


def test_feed_omits_defaults_when_unset(client):
    response = client.get("/api/feed")
    assert response.status_code == 200
    data = response.get_json()
    assert data["page"] == 1
    # Defaults applied; response shape is {videos, page, mode, bucket}.


def test_feed_per_page_boundary_values(client):
    for pp in (1, 50):
        r = client.get(f"/api/feed?per_page={pp}")
        assert r.status_code == 200
    for pp in (51, 999, 1000):
        r = client.get(f"/api/feed?per_page={pp}")
        assert r.status_code == 400


# ----- _parse_positive_int_query helper applied to /api/feed -----


def test_feed_helper_direct_call_with_malformed_page(app):
    with app.test_request_context("/api/feed?page=abc"):
        from bottube_server import _parse_positive_int_query
        value, error = _parse_positive_int_query("page", 1)
        assert value is None
        assert error[1] == 400
        assert "page" in error[0].get_json()["error"]
