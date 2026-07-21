"""Tests for shared query-parameter validators.

Covers parse_int_param, parse_enum_param, parse_ts_param across
the 4 endpoints reported in issues #1456, #1436, #1435, #1468.
"""

import pytest
from unittest.mock import patch
from flask import Flask, request

from bottube.param_validators import parse_int_param, parse_enum_param, parse_ts_param


@pytest.fixture
def app():
    return Flask(__name__)


@pytest.fixture
def ctx(app):
    with app.test_request_context():
        yield


# ── parse_int_param ────────────────────────────────────────


class TestParseIntParam:
    def test_missing_uses_default(self, ctx):
        assert parse_int_param("limit", 20) == (20, None)

    def test_valid(self, ctx):
        with patch.object(request, "args", {"limit": "10"}):
            assert parse_int_param("limit", 20) == (10, None)

    def test_malformed_string(self, ctx):
        with patch.object(request, "args", {"limit": "abc"}):
            val, err = parse_int_param("limit", 20)
            assert val is None
            assert err[1] == 400

    def test_negative_rejected(self, ctx):
        with patch.object(request, "args", {"page": "-5"}):
            val, err = parse_int_param("page", 1, min_value=1)
            assert val is None
            assert err[1] == 400

    def test_oversized_rejected(self, ctx):
        with patch.object(request, "args", {"page": "99999"}):
            val, err = parse_int_param("page", 1, min_value=1, max_value=50)
            assert val is None
            assert err[1] == 400

    def test_zero_rejected_with_min1(self, ctx):
        with patch.object(request, "args", {"limit": "0"}):
            val, err = parse_int_param("limit", 20, min_value=1)
            assert val is None
            assert err[1] == 400

    def test_clamp(self, ctx):
        with patch.object(request, "args", {"limit": "200"}):
            val, err = parse_int_param("limit", 20, min_value=1, max_value=50, clamp=True)
            assert val == 50
            assert err is None

    def test_empty_string_uses_default(self, ctx):
        with patch.object(request, "args", {"limit": ""}):
            assert parse_int_param("limit", 20) == (20, None)


# ── parse_enum_param ────────────────────────────────────────


class TestParseEnumParam:
    def test_missing_uses_default(self, ctx):
        assert parse_enum_param("mode", ["latest", "recommended"], "latest") == ("latest", None)

    def test_valid_enum(self, ctx):
        with patch.object(request, "args", {"mode": "recommended"}):
            val, err = parse_enum_param("mode", ["latest", "recommended"])
            assert val == "recommended"
            assert err is None

    def test_invalid_rejected(self, ctx):
        with patch.object(request, "args", {"mode": "invalid_mode"}):
            val, err = parse_enum_param("mode", ["latest", "recommended"])
            assert val is None
            assert err[1] == 400

    def test_case_insensitive(self, ctx):
        with patch.object(request, "args", {"mode": "LATEST"}):
            val, err = parse_enum_param("mode", ["latest", "recommended"], case_sensitive=False)
            assert val == "latest"
            assert err is None

    def test_empty_string_uses_default(self, ctx):
        with patch.object(request, "args", {"mode": ""}):
            val, err = parse_enum_param("mode", ["latest", "recommended"], "latest")
            assert val == "latest"
            assert err is None


# ── parse_ts_param ─────────────────────────────────────────


class TestParseTsParam:
    def test_missing_uses_default(self, ctx):
        assert parse_ts_param("since") == (None, None)

    def test_valid_timestamp(self, ctx):
        with patch.object(request, "args", {"since": "1742400000"}):
            val, err = parse_ts_param("since")
            assert val == 1742400000.0
            assert err is None

    def test_valid_float(self, ctx):
        with patch.object(request, "args", {"since": "1742400000.5"}):
            val, err = parse_ts_param("since")
            assert val == 1742400000.5
            assert err is None

    def test_malformed_rejected(self, ctx):
        with patch.object(request, "args", {"since": "not-a-timestamp"}):
            val, err = parse_ts_param("since")
            assert val is None
            assert err[1] == 400

    def test_negative_rejected(self, ctx):
        with patch.object(request, "args", {"since": "-1"}):
            val, err = parse_ts_param("since")
            assert val is None
            assert err[1] == 400

    def test_nan_rejected(self, ctx):
        with patch.object(request, "args", {"since": "nan"}):
            val, err = parse_ts_param("since")
            assert val is None
            assert err[1] == 400
