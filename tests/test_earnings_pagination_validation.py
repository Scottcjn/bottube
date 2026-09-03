# SPDX-License-Identifier: MIT
"""Strict pagination regressions for the authenticated earnings ledger."""

def test_earnings_pagination_contract(client, registered_agent):
    headers = {"X-API-Key": registered_agent["api_key"]}
    invalid_queries = [
        {"page": "abc"},
        {"page": "1.5"},
        {"page": "0"},
        {"page": "-1"},
        {"per_page": "abc"},
        {"per_page": "1.5"},
        {"per_page": "0"},
        {"per_page": "-1"},
        {"per_page": "101"},
        {"page": str(2 ** 63)},
    ]
    for query in invalid_queries:
        response = client.get(
            "/api/agents/me/earnings", query_string=query, headers=headers,
        )
        assert response.status_code == 400, (query, response.get_json())
        assert response.get_json().get("error")

    valid_queries = [
        ({}, 1, 50),
        ({"page": "2", "per_page": "100"}, 2, 100),
    ]
    for query, expected_page, expected_per_page in valid_queries:
        response = client.get(
            "/api/agents/me/earnings", query_string=query, headers=headers,
        )
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["page"] == expected_page
        assert response.get_json()["per_page"] == expected_per_page
