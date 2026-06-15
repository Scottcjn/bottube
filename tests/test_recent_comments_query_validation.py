# SPDX-License-Identifier: MIT
import pytest


@pytest.mark.parametrize(
    ("value", "expected_error"),
    [
        ("abc", "limit must be an integer"),
        ("-1", "limit must be >= 1"),
        ("0", "limit must be >= 1"),
        ("101", "limit must be <= 100"),
        ("999999999999999", "limit must be <= 100"),
    ],
)
def test_recent_comments_rejects_malformed_or_out_of_range_limit(
    client, value, expected_error
):
    response = client.get(f"/api/comments/recent?limit={value}")

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}


@pytest.mark.parametrize("value", ["1", "100"])
def test_recent_comments_accepts_limit_boundaries(client, value):
    response = client.get(f"/api/comments/recent?limit={value}")

    assert response.status_code == 200


def test_recent_comments_rejects_malformed_since(client):
    response = client.get("/api/comments/recent?since=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "since must be a number"}


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_recent_comments_rejects_non_finite_since(client, value):
    response = client.get(f"/api/comments/recent?since={value}")

    assert response.status_code == 400
    assert response.get_json() == {"error": "since must be a finite number"}
