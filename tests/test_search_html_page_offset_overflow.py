"""Regression coverage for the HTML search page pagination boundary."""


def test_search_page_rejects_offset_above_sqlite_integer_range(client):
    response = client.get("/search?q=video&page=9223372036854775807")

    assert response.status_code == 400
    assert response.get_json() == {"error": "page out of range"}


def test_search_page_allows_large_safe_page(client):
    response = client.get("/search?q=video&page=1000000000")

    assert response.status_code == 200
