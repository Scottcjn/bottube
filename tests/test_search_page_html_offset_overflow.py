# SPDX-License-Identifier: MIT
"""Regression tests for SQLite OFFSET overflow on the HTML search page."""


_SQLITE_MAX_SIGNED_INT = 2 ** 63 - 1


def test_search_page_rejects_page_whose_offset_overflows_sqlite(client):
    """A huge positive page must return 400 instead of raising in SQLite."""
    response = client.get(f"/search?q=x&page={_SQLITE_MAX_SIGNED_INT}")

    assert response.status_code == 400
    assert response.get_json() == {"error": "page out of range"}


def test_search_page_normal_pagination_still_renders(client):
    """Ordinary search pagination must continue to render the HTML page."""
    response = client.get("/search?q=x&page=1")

    assert response.status_code == 200
    assert b"Search" in response.data


def test_empty_search_rejects_an_invalid_page_before_sql(client):
    """The pagination contract remains strict even when the query is empty."""
    response = client.get(f"/search?page={_SQLITE_MAX_SIGNED_INT}")

    assert response.status_code == 400
    assert response.get_json() == {"error": "page out of range"}
