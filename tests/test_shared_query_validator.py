# SPDX-License-Identifier: MIT
"""Tests for shared_query_validator module.

Covers parse_int_param, parse_enum_param, parse_ts_param with malformed/negative/oversized/valid inputs.
"""
import pytest
from flask import Flask, jsonify, request
from shared_query_validator import parse_int_param, parse_enum_param, parse_ts_param


@pytest.fixture
def app():
    app = Flask(__name__)
    return app


def test_parse_int_param_default_when_missing(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("limit", default=20, min_value=1, max_value=50)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.json["value"] == 20


def test_parse_int_param_default_when_empty(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("limit", default=20, min_value=1, max_value=50)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?limit=")
        assert resp.status_code == 200
        assert resp.json["value"] == 20


def test_parse_int_param_valid_value(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("limit", default=20, min_value=1, max_value=50)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?limit=10")
        assert resp.status_code == 200
        assert resp.json["value"] == 10


def test_parse_int_param_malformed_string(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("limit", default=20, min_value=1, max_value=50)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?limit=abc")
        assert resp.status_code == 400
        assert "integer" in resp.json["error"].lower()


def test_parse_int_param_negative_value(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("limit", default=20, min_value=1, max_value=50)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?limit=-5")
        assert resp.status_code == 400
        assert ">= 1" in resp.json["error"]


def test_parse_int_param_oversized_value(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("limit", default=20, min_value=1, max_value=50)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?limit=999")
        assert resp.status_code == 400
        assert "<= 50" in resp.json["error"]


def test_parse_int_param_zero_value_with_min_one(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("page", default=1, min_value=1, max_value=100)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?page=0")
        assert resp.status_code == 400


def test_parse_int_param_no_bounds(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("anything", default=0)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?anything=12345")
        assert resp.status_code == 200
        assert resp.json["value"] == 12345


def test_parse_int_param_min_only(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("min_test", default=0, min_value=5)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?min_test=3")
        assert resp.status_code == 400


def test_parse_enum_param_valid_value(app):
    @app.route("/test")
    def handler():
        value, err = parse_enum_param("mode", {"latest", "recommended"}, default="latest")
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?mode=recommended")
        assert resp.status_code == 200
        assert resp.json["value"] == "recommended"


def test_parse_enum_param_invalid_value(app):
    @app.route("/test")
    def handler():
        value, err = parse_enum_param("mode", {"latest", "recommended"}, default="latest")
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?mode=invalid")
        assert resp.status_code == 400
        assert "one of" in resp.json["error"].lower()


def test_parse_enum_param_default_when_missing(app):
    @app.route("/test")
    def handler():
        value, err = parse_enum_param("mode", {"latest", "recommended"}, default="latest")
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.json["value"] == "latest"


def test_parse_enum_param_case_insensitive(app):
    @app.route("/test")
    def handler():
        value, err = parse_enum_param("mode", {"latest", "recommended"}, default="latest")
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?mode=LATEST")
        assert resp.status_code == 200
        assert resp.json["value"] == "latest"


def test_parse_ts_param_valid_timestamp(app):
    @app.route("/test")
    def handler():
        value, err = parse_ts_param("since", default=0, min_value=0)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?since=1700000000.5")
        assert resp.status_code == 200
        assert resp.json["value"] == pytest.approx(1700000000.5)


def test_parse_ts_param_nan_rejected(app):
    @app.route("/test")
    def handler():
        value, err = parse_ts_param("since", default=0, min_value=0)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?since=nan")
        assert resp.status_code == 400


def test_parse_ts_param_inf_rejected(app):
    @app.route("/test")
    def handler():
        value, err = parse_ts_param("since", default=0, min_value=0)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?since=inf")
        assert resp.status_code == 400


def test_parse_ts_param_negative_rejected(app):
    @app.route("/test")
    def handler():
        value, err = parse_ts_param("since", default=0, min_value=0)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?since=-100")
        assert resp.status_code == 400


def test_parse_ts_param_default_when_missing(app):
    @app.route("/test")
    def handler():
        value, err = parse_ts_param("since", default=0, min_value=0)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.json["value"] == 0


def test_parse_ts_param_malformed_rejected(app):
    @app.route("/test")
    def handler():
        value, err = parse_ts_param("since", default=0, min_value=0)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?since=not_a_number")
        assert resp.status_code == 400
        assert "number" in resp.json["error"].lower()


def test_parse_int_param_boundary_values(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("limit", default=20, min_value=1, max_value=50)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?limit=1")
        assert resp.status_code == 200
        assert resp.json["value"] == 1

        resp = client.get("/test?limit=50")
        assert resp.status_code == 200
        assert resp.json["value"] == 50


def test_parse_int_param_float_string_rejected(app):
    @app.route("/test")
    def handler():
        value, err = parse_int_param("limit", default=20, min_value=1, max_value=50)
        if err:
            return err
        return jsonify({"value": value})

    with app.test_client() as client:
        resp = client.get("/test?limit=3.14")
        assert resp.status_code == 400
