"""Regression coverage for webhook registration field contracts."""


def test_webhook_registration_rejects_structured_fields_before_insert(app, client, registered_agent):
    headers = {"X-API-Key": registered_agent["api_key"]}
    invalid_payloads = (
        {"url": {"href": "https://example.com/hook"}},
        {"url": "https://example.com/hook", "events": {"name": "video.uploaded"}},
        {"url": "https://example.com/hook", "events": 7},
        {"url": "https://example.com/hook", "events": ["video.uploaded", 7]},
    )

    for payload in invalid_payloads:
        response = client.post("/api/webhooks", headers=headers, json=payload)
        assert response.status_code == 400, (payload, response.get_json())

    import bottube_server

    with app.app_context():
        count = bottube_server.get_db().execute(
            "SELECT COUNT(*) FROM webhooks WHERE agent_id = (SELECT id FROM agents WHERE agent_name = ?)",
            (registered_agent["agent_name"],),
        ).fetchone()[0]
    assert count == 0


def test_webhook_registration_preserves_string_and_string_list_events(client, registered_agent):
    headers = {"X-API-Key": registered_agent["api_key"]}

    first = client.post(
        "/api/webhooks",
        headers=headers,
        json={"url": "https://example.com/first", "events": "video.uploaded"},
    )
    second = client.post(
        "/api/webhooks",
        headers=headers,
        json={"url": "https://example.com/second", "events": ["video.uploaded", "comment.created"]},
    )

    assert first.status_code == 201
    assert first.get_json()["events"] == "video.uploaded"
    assert second.status_code == 201
    assert second.get_json()["events"] == "video.uploaded,comment.created"
