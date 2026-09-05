# SPDX-License-Identifier: MIT
def test_earnings_reject_invalid_pagination(client, registered_agent):
    invalid_queries = (
        "page=abc",
        "page=0",
        "page=-1",
        "page=10001",
        "per_page=abc",
        "per_page=0",
        "per_page=101",
    )

    for query in invalid_queries:
        response = client.get(
            f"/api/agents/me/earnings?{query}",
            headers={"X-API-Key": registered_agent["api_key"]},
        )

        assert response.status_code == 400, query
        assert response.get_json()["error"], query
