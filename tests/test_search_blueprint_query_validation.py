# SPDX-License-Identifier: MIT
"""Query validation tests for standalone discoverability blueprint endpoints."""

import pytest
from flask import Flask

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
    resp = discover_client.get(path)

    assert resp.status_code == 400
    assert "Invalid" in resp.get_json()["error"]
