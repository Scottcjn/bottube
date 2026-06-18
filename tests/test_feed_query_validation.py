import pytest


@pytest.mark.parametrize(
    ("query", "error"),
    [
        ("page=abc", {"error": "page must be an integer"}),
        ("page=0", {"error": "page must be between 1 and 10000"}),
        ("page=10001", {"error": "page must be between 1 and 10000"}),
        ("per_page=abc", {"error": "per_page must be an integer"}),
        ("per_page=0", {"error": "per_page must be between 1 and 50"}),
        ("per_page=51", {"error": "per_page must be between 1 and 50"}),
        ("mode=sideways", {"error": "mode must be one of: latest, recommended"}),
        ("category=not-a-category", {"error": "category must be a known category"}),
        ("bucket=unknown", {"error": "bucket must be one of: latest, heuristic, hybrid-v1"}),
    ],
)
def test_feed_rejects_malformed_query_params(client, query, error):
    response = client.get(f"/api/feed?{query}")

    assert response.status_code == 400
    assert response.get_json() == error
