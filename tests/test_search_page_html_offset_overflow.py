# SPDX-License-Identifier: MIT
"""Regression coverage for HTML search pagination bounds."""


def test_search_page_rejects_offset_overflow(client):
    response = client.get("/search?q=video&page=9223372036854775807")

    assert response.status_code == 400
    assert b"page" in response.data.lower()


def test_search_page_keeps_large_safe_pages(client):
    response = client.get("/search?q=video&page=1000000000")

    assert response.status_code == 200
