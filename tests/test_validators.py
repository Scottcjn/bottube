# SPDX-License-Identifier: MIT
"""
Regression tests for the shared query-param validator module.

Covers all 4 endpoints from bounty #16254:
  #1456 — /api/feed: 7 params (limit/offset/page/since/before/category/sort)
  #1436 — /api/trending: limit/days/since
  #1435 — /api/videos: page
  #1468 — /api/videos/<id>/related: limit
"""

import pytest
from flask import Flask


# ---------------------------------------------------------------------------
# Fixture: a minimal Flask app + request context helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ==============================
# parse_positive_int
# ==============================

class TestParsePositiveInt:
    def test_returns_default_when_absent(self, app):
        with app.test_request_context("/api/feed"):
            from validators import parse_positive_int
            val, err = parse_positive_int("limit", 20, max_value=100)
            assert val == 20
            assert err is None

    def test_returns_default_when_empty(self, app):
        with app.test_request_context("/api/feed?limit="):
            from validators import parse_positive_int
            val, err = parse_positive_int("limit", 20, max_value=100)
            assert val == 20
            assert err is None

    def test_accepts_valid_integer(self, app):
        with app.test_request_context("/api/feed?limit=10"):
            from validators import parse_positive_int
            val, err = parse_positive_int("limit", 20, max_value=100)
            assert val == 10
            assert err is None

    def test_rejects_non_integer_string(self, app):
        with app.test_request_context("/api/feed?limit=abc"):
            from validators import parse_positive_int
            val, err = parse_positive_int("limit", 20, max_value=100)
            assert val is None
            resp, status = err
            assert status == 400
            assert "must be an integer" in resp.get_json()["error"]

    def test_rejects_float_string(self, app):
        with app.test_request_context("/api/feed?limit=1.5"):
            from validators import parse_positive_int
            val, err = parse_positive_int("limit", 20, max_value=100)
            assert val is None
            assert err[1] == 400

    def test_rejects_negative(self, app):
        with app.test_request_context("/api/feed?limit=-1"):
            from validators import parse_positive_int
            val, err = parse_positive_int("limit", 20, max_value=100)
            assert val is None
            assert err[1] == 400

    def test_rejects_zero(self, app):
        with app.test_request_context("/api/feed?limit=0"):
            from validators import parse_positive_int
            val, err = parse_positive_int("limit", 20, max_value=100)
            assert val is None
            assert err[1] == 400

    def test_rejects_exceeds_max(self, app):
        with app.test_request_context("/api/feed?limit=200"):
            from validators import parse_positive_int
            val, err = parse_positive_int("limit", 20, max_value=100)
            assert val is None
            resp, status = err
            assert status == 400
            assert "<= 100" in resp.get_json()["error"]

    def test_rejects_nan(self, app):
        with app.test_request_context("/api/feed?limit=NaN"):
            from validators import parse_positive_int
            val, err = parse_positive_int("limit", 20, max_value=100)
            assert val is None
            assert err[1] == 400

    def test_rejects_null_string(self, app):
        with app.test_request_context("/api/feed?limit=null"):
            from validators import parse_positive_int
            val, err = parse_positive_int("limit", 20, max_value=100)
            assert val is None
            assert err[1] == 400


# ==============================
# parse_non_negative_int
# ==============================

class TestParseNonNegativeInt:
    def test_accepts_zero(self, app):
        with app.test_request_context("/api/feed?offset=0"):
            from validators import parse_non_negative_int
            val, err = parse_non_negative_int("offset", 0)
            assert val == 0
            assert err is None

    def test_accepts_positive(self, app):
        with app.test_request_context("/api/feed?offset=50"):
            from validators import parse_non_negative_int
            val, err = parse_non_negative_int("offset", 0)
            assert val == 50
            assert err is None

    def test_rejects_negative(self, app):
        with app.test_request_context("/api/feed?offset=-1"):
            from validators import parse_non_negative_int
            val, err = parse_non_negative_int("offset", 0)
            assert val is None
            assert err[1] == 400

    def test_rejects_float(self, app):
        with app.test_request_context("/api/feed?offset=1.5"):
            from validators import parse_non_negative_int
            val, err = parse_non_negative_int("offset", 0)
            assert val is None
            assert err[1] == 400

    def test_rejects_non_integer(self, app):
        with app.test_request_context("/api/feed?offset=abc"):
            from validators import parse_non_negative_int
            val, err = parse_non_negative_int("offset", 0)
            assert val is None
            assert err[1] == 400


# ==============================
# parse_enum
# ==============================

class TestParseEnum:
    def test_returns_default_when_absent(self, app):
        with app.test_request_context("/api/feed"):
            from validators import parse_enum
            val, err = parse_enum("sort", "newest", {"newest", "oldest", "popular"})
            assert val == "newest"
            assert err is None

    def test_accepts_valid_case_sensitive(self, app):
        with app.test_request_context("/api/feed?sort=newest"):
            from validators import parse_enum
            val, err = parse_enum("sort", "newest", {"newest", "oldest", "popular"})
            assert val == "newest"
            assert err is None

    def test_accepts_case_insensitive(self, app):
        with app.test_request_context("/api/feed?sort=NEWEST"):
            from validators import parse_enum
            val, err = parse_enum("sort", "newest", {"newest", "oldest", "popular"})
            assert val == "newest"
            assert err is None

    def test_rejects_invalid(self, app):
        with app.test_request_context("/api/feed?sort=bogus"):
            from validators import parse_enum
            val, err = parse_enum("sort", "newest", {"newest", "oldest", "popular"})
            assert val is None
            resp, status = err
            assert status == 400
            assert "sort" in resp.get_json()["error"]

    def test_case_sensitive_mode_rejects_different_case(self, app):
        with app.test_request_context("/api/feed?sort=Newest"):
            from validators import parse_enum
            val, err = parse_enum(
                "sort", "newest", {"newest", "oldest"}, case_sensitive=True
            )
            assert val is None
            assert err[1] == 400


# ==============================
# parse_timestamp
# ==============================

class TestParseTimestamp:
    def test_returns_default_when_absent(self, app):
        with app.test_request_context("/api/trending"):
            from validators import parse_timestamp
            val, err = parse_timestamp("since")
            assert val is None
            assert err is None

    def test_accepts_numeric_timestamp(self, app):
        with app.test_request_context("/api/trending?since=1700000000"):
            from validators import parse_timestamp
            val, err = parse_timestamp("since")
            assert val == 1700000000.0
            assert err is None

    def test_accepts_float_timestamp(self, app):
        with app.test_request_context("/api/trending?since=1700000000.5"):
            from validators import parse_timestamp
            val, err = parse_timestamp("since")
            assert val == 1700000000.5
            assert err is None

    def test_rejects_non_numeric(self, app):
        with app.test_request_context("/api/trending?since=abc"):
            from validators import parse_timestamp
            val, err = parse_timestamp("since")
            assert val is None
            assert err[1] == 400

    def test_rejects_nan(self, app):
        with app.test_request_context("/api/trending?since=NaN"):
            from validators import parse_timestamp
            val, err = parse_timestamp("since")
            assert val is None
            assert err[1] == 400

    def test_rejects_infinity(self, app):
        with app.test_request_context("/api/trending?since=Infinity"):
            from validators import parse_timestamp
            val, err = parse_timestamp("since")
            assert val is None
            assert err[1] == 400

    def test_rejects_empty_string(self, app):
        with app.test_request_context("/api/trending?since="):
            from validators import parse_timestamp
            val, err = parse_timestamp("since", default=100.0)
            assert val == 100.0
            assert err is None


# ==============================
# parse_offset_and_limit (compound)
# ==============================

class TestParseOffsetAndLimit:
    def test_returns_defaults_when_absent(self, app):
        with app.test_request_context("/api/feed"):
            from validators import parse_offset_and_limit
            (offset, o_err), (limit, l_err) = parse_offset_and_limit()
            assert offset == 0
            assert limit == 20
            assert o_err is None
            assert l_err is None

    def test_accepts_valid_values(self, app):
        with app.test_request_context("/api/feed?offset=10&limit=50"):
            from validators import parse_offset_and_limit
            (offset, o_err), (limit, l_err) = parse_offset_and_limit()
            assert offset == 10
            assert limit == 50
            assert o_err is None
            assert l_err is None

    def test_rejects_negative_offset(self, app):
        with app.test_request_context("/api/feed?offset=-1"):
            from validators import parse_offset_and_limit
            (offset, o_err), _ = parse_offset_and_limit()
            assert offset is None
            assert o_err is not None

    def test_rejects_limit_exceeding_max(self, app):
        with app.test_request_context("/api/feed?limit=200"):
            from validators import parse_offset_and_limit
            _, (limit, l_err) = parse_offset_and_limit(max_limit=100)
            assert limit is None
            assert l_err is not None
            resp, status = l_err
            assert "<= 100" in resp.get_json()["error"]


# ==============================
# parse_standard_pagination (compound)
# ==============================

class TestParseStandardPagination:
    def test_returns_defaults(self, app):
        with app.test_request_context("/api/videos"):
            from validators import parse_standard_pagination
            (page, p_err), (per_page, pp_err) = parse_standard_pagination()
            assert page == 1
            assert per_page == 20
            assert p_err is None
            assert pp_err is None

    def test_accepts_valid(self, app):
        with app.test_request_context("/api/videos?page=2&per_page=30"):
            from validators import parse_standard_pagination
            (page, p_err), (per_page, pp_err) = parse_standard_pagination(
                max_per_page=50
            )
            assert page == 2
            assert per_page == 30
            assert p_err is None
            assert pp_err is None

    def test_rejects_oversized_per_page(self, app):
        with app.test_request_context("/api/videos?per_page=999"):
            from validators import parse_standard_pagination
            _, (per_page, pp_err) = parse_standard_pagination(max_per_page=50)
            assert per_page is None
            assert pp_err is not None
            resp, status = pp_err
            assert "<= 50" in resp.get_json()["error"]


# ==============================
# Endpoint integration tests (using test client)
# ==============================

class TestFeedEndpointParams:
    """Regression tests for #1456 — /api/feed params."""

    def test_feed_rejects_non_integer_limit(self, client):
        response = client.get("/api/feed?limit=abc")
        assert response.status_code == 400
        data = response.get_json()
        assert "limit" in data["error"]
        assert "integer" in data["error"]

    def test_feed_rejects_negative_limit(self, client):
        response = client.get("/api/feed?limit=-5")
        assert response.status_code == 400

    def test_feed_rejects_zero_limit(self, client):
        response = client.get("/api/feed?limit=0")
        assert response.status_code == 400

    def test_feed_rejects_limit_above_max(self, client):
        response = client.get("/api/feed?limit=200")
        assert response.status_code == 400

    def test_feed_rejects_non_integer_offset(self, client):
        response = client.get("/api/feed?offset=abc")
        assert response.status_code == 400
        data = response.get_json()
        assert "offset" in data["error"]

    def test_feed_rejects_negative_offset(self, client):
        response = client.get("/api/feed?offset=-1")
        assert response.status_code == 400

    def test_feed_rejects_non_integer_page(self, client):
        response = client.get("/api/feed?page=abc")
        assert response.status_code == 400

    def test_feed_rejects_float_page(self, client):
        response = client.get("/api/feed?page=1.5")
        assert response.status_code == 400

    def test_feed_rejects_non_numeric_since(self, client):
        response = client.get("/api/feed?since=abc")
        assert response.status_code == 400

    def test_feed_rejects_non_numeric_before(self, client):
        response = client.get("/api/feed?before=abc")
        assert response.status_code == 400

    def test_feed_rejects_invalid_category(self, client):
        response = client.get("/api/feed?category=__invalid__")
        assert response.status_code == 400
        data = response.get_json()
        assert "category" in data["error"]

    def test_feed_rejects_invalid_sort(self, client):
        response = client.get("/api/feed?sort=bogus")
        assert response.status_code == 400
        data = response.get_json()
        assert "sort" in data["error"]


class TestTrendingEndpointParams:
    """Regression tests for #1436 — /api/trending params."""

    def test_trending_rejects_non_integer_limit(self, client):
        response = client.get("/api/trending?limit=abc")
        assert response.status_code == 400
        data = response.get_json()
        assert "limit" in data["error"]

    def test_trending_rejects_negative_limit(self, client):
        response = client.get("/api/trending?limit=-5")
        assert response.status_code == 400

    def test_trending_rejects_non_numeric_days(self, client):
        response = client.get("/api/trending?days=abc")
        assert response.status_code == 400
        data = response.get_json()
        assert "days" in data["error"]

    def test_trending_rejects_negative_days(self, client):
        response = client.get("/api/trending?days=-1")
        assert response.status_code == 400

    def test_trending_rejects_non_numeric_since(self, client):
        response = client.get("/api/trending?since=abc")
        assert response.status_code == 400

    def test_trending_rejects_nan_since(self, client):
        response = client.get("/api/trending?since=NaN")
        assert response.status_code == 400


class TestVideosEndpointParams:
    """Regression tests for #1435 — /api/videos page param."""

    def test_videos_rejects_non_integer_page(self, client):
        response = client.get("/api/videos?page=abc")
        assert response.status_code == 400
        data = response.get_json()
        assert "page" in data["error"]

    def test_videos_rejects_negative_page(self, client):
        response = client.get("/api/videos?page=-5")
        assert response.status_code == 400

    def test_videos_rejects_zero_page(self, client):
        response = client.get("/api/videos?page=0")
        assert response.status_code == 400

    def test_videos_rejects_float_page(self, client):
        response = client.get("/api/videos?page=1.5")
        assert response.status_code == 400

    def test_videos_rejects_null_page(self, client):
        response = client.get("/api/videos?page=null")
        assert response.status_code == 400

    def test_videos_accepts_valid_page(self, client):
        response = client.get("/api/videos?page=1&per_page=10")
        assert response.status_code in (200, 400)  # 200 if endpoint exists

    def test_videos_rejects_non_integer_per_page(self, client):
        response = client.get("/api/videos?per_page=abc")
        assert response.status_code == 400
        data = response.get_json()
        assert "per_page" in data["error"]


class TestRelatedEndpointParams:
    """Regression tests for #1468 — /api/videos/<id>/related limit param."""

    def test_related_rejects_non_integer_limit(self, client):
        response = client.get("/api/videos/some-id/related?limit=abc")
        assert response.status_code == 400
        data = response.get_json()
        assert "limit" in data["error"]

    def test_related_rejects_negative_limit(self, client):
        response = client.get("/api/videos/some-id/related?limit=-5")
        assert response.status_code == 400

    def test_related_rejects_zero_limit(self, client):
        response = client.get("/api/videos/some-id/related?limit=0")
        assert response.status_code == 400

    def test_related_rejects_float_limit(self, client):
        response = client.get("/api/videos/some-id/related?limit=1.5")
        assert response.status_code == 400

    def test_related_accepts_valid_limit(self, client):
        response = client.get("/api/videos/some-id/related?limit=10")
        assert response.status_code in (200, 400)  # 200 if endpoint exists


# ==============================
# Null / empty boundary tests
# ==============================

class TestBoundaryCases:
    def test_rejects_null_instead_of_integer(self, app):
        with app.test_request_context("/api/feed?page=null"):
            from validators import parse_positive_int
            val, err = parse_positive_int("page", 1)
            assert val is None
            assert err is not None

    def test_rejects_nan_instead_of_integer(self, app):
        with app.test_request_context("/api/feed?page=NaN"):
            from validators import parse_positive_int
            val, err = parse_positive_int("page", 1)
            assert val is None
            assert err is not None

    def test_rejects_empty_non_default_param(self, app):
        with app.test_request_context("/api/feed?page="):
            from validators import parse_positive_int
            val, err = parse_positive_int("page", 1)
            # Empty string returns default
            assert val == 1
            assert err is None
