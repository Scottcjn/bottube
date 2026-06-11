# SPDX-License-Identifier: MIT
import pytest


def test_recent_comments_rejects_malformed_limit(client):
    response = client.get("/api/comments/recent?limit=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "limit must be an integer"}


def test_recent_comments_rejects_malformed_since(client):
    response = client.get("/api/comments/recent?since=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "since must be a number"}


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_recent_comments_rejects_non_finite_since(client, value):
    response = client.get(f"/api/comments/recent?since={value}")

    assert response.status_code == 400
    assert response.get_json() == {"error": "since must be a finite number"}

