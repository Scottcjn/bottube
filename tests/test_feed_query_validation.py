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
    response = client.get(f"/api/feed?{query}")

    assert response.status_code == 400
    assert "must be one of" in response.get_json()["error"]


def test_feed_accepts_known_filter_options(client):
    response = client.get("/api/feed?mode=latest&bucket=latest&category=music")

    assert response.status_code == 200
    data = response.get_json()
    assert data["mode"] == "latest"
    assert data["bucket"] == "latest"
