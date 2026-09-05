# SPDX-License-Identifier: MIT
"""Query validation tests for standalone discoverability blueprint endpoints."""

import pytest
from flask import Flask

import search_blueprint
from search_blueprint import search_bp


@pytest.fixture()
def discover_client():
    app = Flask(__name__)
    app.register_blueprint(search_bp)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.parametrize(
    "path",
    [
        "/discover/api/tags?limit=not-an-int",
        "/discover/api/tag/python?limit=not-an-int",
        "/discover/api/tag/python?offset=not-an-int",
        "/discover/api/trending?limit=not-an-int",
        "/discover/api/for-you?limit=not-an-int",
    ],
)
def test_discoverability_endpoints_reject_malformed_integer_params(discover_client, path):
    """Verify discoverability endpoints reject non-integer limit/offset.

    The /discover/api/* endpoints (tags, tag/{slug}, trending, for-you)
    accept limit and offset as integer query params. Non-integer values
    (e.g. `limit=not-an-int`, `offset=not-an-int`) must be rejected with
    a 400 and an error message containing 'expected an integer' so the
    SDK can show a precise validation hint instead of a 500 from int().
    """
    resp = discover_client.get(path)

    assert resp.status_code == 400
    assert "expected an integer" in resp.get_json()["error"]


@pytest.mark.parametrize(
    "path",
    [
        "/discover/api/tags?limit=0",
        "/discover/api/tag/python?limit=0",
        "/discover/api/tag/python?offset=-1",
        "/discover/api/trending?limit=0",
        "/discover/api/for-you?limit=0",
    ],
)
def test_discoverability_endpoints_reject_out_of_range_integer_params(discover_client, path):
    """Verify discoverability endpoints reject out-of-range limit/offset.

    Mirrors the malformed-integer test above but for integer values that
    are out of the allowed range (limit=0, offset=-1). These must 400
    with an error message containing 'Invalid' so clients can tell the
    difference between a parse failure and a range failure.
    """
    resp = discover_client.get(path)

    assert resp.status_code == 400
    assert "Invalid" in resp.get_json()["error"]


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("category=definitely-not-a-category", "category"),
        ("q=robot&sort=definitely-not-a-sort", "sort"),
    ],
)
def test_discover_search_rejects_unknown_enum_values(
    discover_client,
    monkeypatch,
    query,
    field,
):
    def fail_db():
        raise AssertionError("invalid search options must fail before querying")

    monkeypatch.setattr(search_blueprint, "get_db", fail_db)

    resp = discover_client.get(f"/discover/api/search?{query}")

    assert resp.status_code == 400
    assert field in resp.get_json()["error"]
