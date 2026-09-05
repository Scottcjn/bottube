# SPDX-License-Identifier: MIT
"""Pagination contracts shared by the admin moderation queues."""

_PATHS = (
    "/api/admin/reports",
    "/api/admin/reward-holds",
    "/api/admin/moderation-holds",
)

_INVALID_QUERIES = (
    "page=abc",
    "page=0",
    "page=10001",
    "page=9223372036854775807",
    "per_page=abc",
    "per_page=0",
)


def test_admin_queue_pagination_contract(client, app, monkeypatch):
    import bottube_server

    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test-admin", raising=False)
    headers = {"X-Admin-Key": "test-admin"}
    real_get_db = bottube_server.get_db

    def fail_if_queried():
        raise AssertionError("invalid pagination reached the database")

    with monkeypatch.context() as invalid_context:
        invalid_context.setattr(bottube_server, "get_db", fail_if_queried)
        for path in _PATHS:
            for query in _INVALID_QUERIES:
                response = client.get(f"{path}?{query}", headers=headers)
                assert response.status_code == 400, (path, query)
                assert response.get_json()["error"], (path, query)

    assert bottube_server.get_db is real_get_db

    valid_bounds = (
        ("/api/admin/reports", 50),
        ("/api/admin/reward-holds", 100),
        ("/api/admin/moderation-holds", 100),
    )
    for path, max_per_page in valid_bounds:
        assert client.get(path, headers=headers).status_code == 200, path
        response = client.get(
            f"{path}?page=10000&per_page={max_per_page}",
            headers=headers,
        )
        assert response.status_code == 200, path

        response = client.get(
            f"{path}?per_page={max_per_page + 1}",
            headers=headers,
        )
        assert response.status_code == 400, path
