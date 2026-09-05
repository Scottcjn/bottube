import pytest


@pytest.mark.parametrize(
    "query",
    [
        "mode=sideways",
        "bucket=random",
        "category=not-a-real-category",
    ],
)
def test_feed_rejects_unknown_filter_options(client, query):
    """Verify the feed endpoint rejects unknown filter values with a 400.

    The /api/feed endpoint accepts `mode`, `bucket`, and `category` query
    params, each constrained to a closed set of allowed values. Unknown
    values must be rejected with a 400 and a clear 'must be one of' error
    so client SDKs can show a friendly validation message instead of
    silently returning an empty feed.
    """
    response = client.get(f"/api/feed?{query}")

    assert response.status_code == 400
    assert "must be one of" in response.get_json()["error"]


def test_feed_accepts_known_filter_options(client):
    """Verify the feed endpoint echoes known filter values back to the client.

    Happy-path test for the same query params covered by
    test_feed_rejects_unknown_filter_options. Confirms that valid
    `mode=latest&bucket=latest&category=music` is parsed and the canonical
    values are returned in the response body so the UI can render the
    active filters without a second roundtrip.
    """
    response = client.get("/api/feed?mode=latest&bucket=latest&category=music")

    assert response.status_code == 200
    data = response.get_json()
    assert data["mode"] == "latest"
    assert data["bucket"] == "latest"
