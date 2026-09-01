# SPDX-License-Identifier: MIT
"""Regression coverage for SQLite OFFSET overflow in the earnings ledger."""


def _headers(agent):
    return {"X-API-Key": agent["api_key"]}


def test_earnings_rejects_page_whose_offset_exceeds_sqlite_integer(client, registered_agent):
    response = client.get(
        "/api/agents/me/earnings?page=9223372036854775807&per_page=100",
        headers=_headers(registered_agent),
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "page out of range"}


def test_earnings_allows_largest_page_with_safe_offset(client, registered_agent):
    max_safe_page = ((2 ** 63 - 1) // 100) + 1
    response = client.get(
        f"/api/agents/me/earnings?page={max_safe_page}&per_page=100",
        headers=_headers(registered_agent),
    )

    assert response.status_code == 200
    assert response.get_json()["earnings"] == []
