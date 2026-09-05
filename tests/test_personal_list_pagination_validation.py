"""Pagination contracts for authenticated personal-list APIs."""

_PATHS = (
    "/api/feed/subscriptions",
    "/api/messages/inbox",
    "/api/history",
)

_INVALID_QUERIES = (
    "page=abc",
    "page=0",
    "page=10001",
    "page=9223372036854775807",
    "per_page=abc",
    "per_page=0",
    "per_page=51",
)


def test_personal_list_apis_reject_invalid_pagination(client, registered_agent):
    headers = {"X-API-Key": registered_agent["api_key"]}

    for path in _PATHS:
        for query in _INVALID_QUERIES:
            response = client.get(f"{path}?{query}", headers=headers)
            assert response.status_code == 400, (path, query, response.get_json())
            assert "error" in response.get_json()


def test_personal_list_apis_accept_pagination_boundaries(client, registered_agent):
    headers = {"X-API-Key": registered_agent["api_key"]}

    for path in _PATHS:
        response = client.get(f"{path}?page=10000&per_page=50", headers=headers)
        assert response.status_code == 200, path
