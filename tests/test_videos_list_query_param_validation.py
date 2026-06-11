# SPDX-License-Identifier: MIT
"""
Regression tests for /api/videos and /api/search rejecting malformed or
out-of-range pagination/sort query parameters with HTTP 400 instead of
silently coercing invalid input to the default.

Bug: `request.args.get("page", 1, type=int)` returns the default (1) for
any non-integer string (e.g. "abc", "1.5", "null", "NaN") and silently
clips to `max(1, ...)` for negatives/zeros.  That swallows client bugs
and produces surprising pagination results.

Fix: shared `_parse_positive_int_query` helper in bottube_server.py.
"""


# ----- /api/videos -----


def test_list_videos_rejects_non_integer_page(client):
    response = client.get("/api/videos?page=abc")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]
    assert "integer" in data["error"]


def test_list_videos_rejects_non_integer_per_page(client):
    response = client.get("/api/videos?per_page=xyz")
    assert response.status_code == 400
    data = response.get_json()
    assert "per_page" in data["error"]


def test_list_videos_rejects_zero_page(client):
    response = client.get("/api/videos?page=0")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]


def test_list_videos_rejects_negative_page(client):
    response = client.get("/api/videos?page=-5")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]


def test_list_videos_rejects_zero_per_page(client):
    response = client.get("/api/videos?per_page=0")
    assert response.status_code == 400
    data = response.get_json()
    assert "per_page" in data["error"]


def test_list_videos_rejects_negative_per_page(client):
    response = client.get("/api/videos?per_page=-1")
    assert response.status_code == 400


def test_list_videos_rejects_per_page_above_max(client):
    # cap is 50; 100 was silently clamped before the fix
    response = client.get("/api/videos?per_page=100")
    assert response.status_code == 400
    data = response.get_json()
    assert "per_page" in data["error"]
    assert "<= 50" in data["error"]


def test_list_videos_rejects_float_page(client):
    response = client.get("/api/videos?page=1.5")
    assert response.status_code == 400


def test_list_videos_rejects_null_page(client):
    response = client.get("/api/videos?page=null")
    assert response.status_code == 400


def test_list_videos_rejects_nan_page(client):
    response = client.get("/api/videos?page=NaN")
    assert response.status_code == 400


def test_list_videos_accepts_valid_pagination(client):
    response = client.get("/api/videos?page=1&per_page=10")
    assert response.status_code == 200
    data = response.get_json()
    assert data["page"] == 1
    assert data["per_page"] == 10


def test_list_videos_omits_defaults_when_unset(client):
    # No page/per_page in the query string -> both default
    response = client.get("/api/videos")
    assert response.status_code == 200
    data = response.get_json()
    assert data["page"] == 1
    assert data["per_page"] == 20


def test_list_videos_per_page_boundary_values(client):
    # min valid = 1, max valid = 50
    for pp in (1, 50):
        r = client.get(f"/api/videos?per_page={pp}")
        assert r.status_code == 200
    for pp in (51, 999, 1000):
        r = client.get(f"/api/videos?per_page={pp}")
        assert r.status_code == 400


# ----- /api/search -----


def test_search_videos_rejects_non_integer_page(client):
    response = client.get("/api/search?q=test&page=abc")
    assert response.status_code == 400
    data = response.get_json()
    assert "page" in data["error"]


def test_search_videos_rejects_non_integer_per_page(client):
    response = client.get("/api/search?q=test&per_page=xyz")
    assert response.status_code == 400
    data = response.get_json()
    assert "per_page" in data["error"]


def test_search_videos_rejects_zero_page(client):
    response = client.get("/api/search?q=test&page=0")
    assert response.status_code == 400


def test_search_videos_rejects_per_page_above_max(client):
    response = client.get("/api/search?q=test&per_page=100")
    assert response.status_code == 400


def test_search_videos_accepts_valid_pagination(client):
    # Empty results is fine, the point is that pagination parsing passed
    response = client.get("/api/search?q=nonexistent_query_xyz&page=1&per_page=10")
    assert response.status_code == 200
    data = response.get_json()
    assert data["page"] == 1
    assert data["per_page"] == 10


def test_search_videos_page_validation_runs_before_query_execution(client):
    # Validation should reject the malformed page param *before* the
    # search-rate-limit is consumed, so a buggy client gets a clear 400
    # instead of a confusing 429.
    response = client.get("/api/search?q=test&page=abc")
    assert response.status_code == 400
    assert "page" in response.get_json()["error"]


# ----- _parse_positive_int_query helper direct coverage -----


def test_parse_helper_allows_missing_param(app):
    with app.test_request_context("/api/videos"):
        from bottube_server import _parse_positive_int_query
        value, error = _parse_positive_int_query("absent", 7)
        assert value == 7
        assert error is None


def test_parse_helper_allows_empty_string(app):
    with app.test_request_context("/api/videos?page="):
        from bottube_server import _parse_positive_int_query
        value, error = _parse_positive_int_query("page", 1)
        assert value == 1
        assert error is None


def test_parse_helper_rejects_non_integer(app):
    with app.test_request_context("/api/videos?page=abc"):
        from bottube_server import _parse_positive_int_query
        value, error = _parse_positive_int_query("page", 1)
        assert value is None
        response, status = error
        assert status == 400
        assert "page" in response.get_json()["error"]


def test_parse_helper_enforces_min(app):
    with app.test_request_context("/api/videos?page=0"):
        from bottube_server import _parse_positive_int_query
        value, error = _parse_positive_int_query("page", 1)
        assert value is None
        assert error[1] == 400


def test_parse_helper_enforces_max(app):
    with app.test_request_context("/api/videos?per_page=999"):
        from bottube_server import _parse_positive_int_query
        value, error = _parse_positive_int_query("per_page", 20, max_value=50)
        assert value is None
        response, status = error
        assert status == 400
        assert "<= 50" in response.get_json()["error"]
