"""Regression coverage for notification preference boolean contracts."""

import sqlite3


def test_notification_preferences_reject_non_booleans_without_mutation(client, registered_agent):
    headers = {"X-API-Key": registered_agent["api_key"]}
    fields = ("comments", "replies", "new_video", "tips", "subscriptions")

    disabled = client.put(
        "/api/notifications/preferences",
        headers=headers,
        json={field: False for field in fields},
    )
    assert disabled.status_code == 200

    for field in fields:
        response = client.put(
            "/api/notifications/preferences",
            headers=headers,
            json={field: "false"},
        )
        assert response.status_code == 400, (field, response.get_json())

    preferences = client.get("/api/notifications/preferences", headers=headers).get_json()["preferences"]
    assert preferences == {field: False for field in fields}


def test_notification_preferences_preserve_valid_partial_booleans(client, registered_agent):
    headers = {"X-API-Key": registered_agent["api_key"]}
    response = client.put(
        "/api/notifications/preferences",
        headers=headers,
        json={"comments": False, "tips": True},
    )

    assert response.status_code == 200
    assert response.get_json()["updated"] == {"comments": False, "tips": True}


def test_browser_notification_preferences_reject_non_booleans(client, registered_agent, app):
    import bottube_server

    with sqlite3.connect(bottube_server.DB_PATH) as db:
        user_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            (registered_agent["agent_name"],),
        ).fetchone()[0]

    with client.session_transaction() as session:
        session["user_id"] = user_id

    response = client.post(
        "/settings/notifications",
        json={"subscriptions": "false"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "subscriptions must be a boolean"}
