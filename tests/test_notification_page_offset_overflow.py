# SPDX-License-Identifier: MIT
"""Regression coverage for SQLite OFFSET overflow in notification lists."""


def _agent_id(app, agent_name):
    with app.app_context():
        import bottube_server

        return bottube_server.get_db().execute(
            "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
        ).fetchone()["id"]


def test_agent_notifications_reject_page_beyond_sqlite_range(app, client, registered_agent):
    response = client.get(
        "/api/agents/me/notifications?page=9223372036854775807&per_page=50",
        headers={"X-API-Key": registered_agent["api_key"]},
    )

    assert response.status_code == 400
    assert "page" in response.get_json()["error"]


def test_web_notifications_reject_page_beyond_sqlite_range(app, client, registered_agent):
    with client.session_transaction() as session:
        session["user_id"] = _agent_id(app, registered_agent["agent_name"])

    response = client.get(
        "/api/notifications?page=9223372036854775807&per_page=50"
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "page out of range"}
