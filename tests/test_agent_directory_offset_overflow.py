"""Regression coverage for agent-directory pagination boundaries."""


def test_agent_directory_rejects_offset_above_sqlite_integer_range(client):
    response = client.get("/api/agents?page=9223372036854775807&limit=100")

    assert response.status_code == 400
    assert response.get_json() == {"error": "page out of range"}


def test_agent_directory_allows_large_safe_page(client):
    response = client.get("/api/agents?page=1000000000&limit=100")

    assert response.status_code == 200
