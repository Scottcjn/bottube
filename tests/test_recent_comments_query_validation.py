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
    """Verify /api/comments/recent rejects malformed or out-of-range limit values.

    The `limit` query param must be an integer in the closed range [1, 100].
    Anything else (non-numeric, negative, zero, or > 100) must 400 with a
    specific error message so clients can surface the failure cause to the
    user. This guards against unbounded result sets and against implicit
    Python coercion (e.g. int('abc') raising 500).
    """
    response = client.get(f"/api/comments/recent?limit={value}")

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}


@pytest.mark.parametrize("value", ["1", "100"])
def test_recent_comments_accepts_limit_boundaries(client, value):
    """Verify /api/comments/recent accepts the limit boundaries 1 and 100.

    Boundary test for the validation covered above: the inclusive lower
    bound (1) and the inclusive upper bound (100) must both return 200.
    Off-by-one regressions in the validator (`>=` vs `>`, `<=` vs `<`)
    would fail this test and over- or under-restrict the response size.
    """
    response = client.get(f"/api/comments/recent?limit={value}")

    assert response.status_code == 200


def test_recent_comments_rejects_malformed_since(client):
    """Verify /api/comments/recent rejects non-numeric `since` values.

    The `since` query param is a unix timestamp (number). A non-numeric
    value must 400 with "since must be a number" instead of crashing
    the SQL parameter binding or returning a 500 from float('abc').
    """
    response = client.get("/api/comments/recent?since=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "since must be a number"}


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_recent_comments_rejects_non_finite_since(client, value):
    """Verify /api/comments/recent rejects NaN and +/-Infinity `since` values.

    JSON allows literal NaN and Infinity (technically invalid JSON, but
    Python's json module accepts them), and so do some HTTP clients. The
    endpoint must reject these explicitly with a 400 and "since must be a
    finite number" because passing NaN/Infinity to a SQL comparison would
    silently match every row (or none) depending on the engine.
    """
    response = client.get(f"/api/comments/recent?since={value}")

    assert response.status_code == 400
    assert response.get_json() == {"error": "since must be a finite number"}
