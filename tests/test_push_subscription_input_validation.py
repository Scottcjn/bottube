# SPDX-License-Identifier: MIT


def _auth_headers(api_key):
    return {"X-API-Key": api_key}


def test_push_subscribe_rejects_non_object_json(client, registered_agent):
    response = client.post(
        "/api/push/subscribe",
        headers=_auth_headers(registered_agent["api_key"]),
        json=["not", "an", "object"],
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON body must be an object"}


def test_push_subscribe_rejects_non_object_keys(client, registered_agent):
    response = client.post(
        "/api/push/subscribe",
        headers=_auth_headers(registered_agent["api_key"]),
        json={"endpoint": "https://push.example/subscription", "keys": "not-an-object"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "keys must be a JSON object"}


def test_push_subscribe_rejects_non_string_fields(client, registered_agent):
    headers = _auth_headers(registered_agent["api_key"])
    cases = [
        ({"endpoint": 7, "keys": {"p256dh": "public", "auth": "secret"}}, "endpoint"),
        ({"endpoint": "https://push.example/subscription", "keys": {"p256dh": 7, "auth": "secret"}}, "p256dh"),
        ({"endpoint": "https://push.example/subscription", "keys": {"p256dh": "public", "auth": 7}}, "auth"),
    ]

    for payload, field in cases:
        response = client.post("/api/push/subscribe", headers=headers, json=payload)
        assert response.status_code == 400
        assert response.get_json() == {"error": f"{field} must be a string"}


def test_push_subscribe_persists_valid_subscription(client, registered_agent, app):
    payload = {
        "endpoint": "https://push.example/subscription",
        "keys": {"p256dh": "public-key", "auth": "auth-secret"},
    }

    response = client.post(
        "/api/push/subscribe",
        headers=_auth_headers(registered_agent["api_key"]),
        json=payload,
    )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}

    with app.app_context():
        import bottube_server

        row = bottube_server.get_db().execute(
            "SELECT endpoint, p256dh, auth FROM push_subscriptions"
        ).fetchone()
        assert dict(row) == {
            "endpoint": payload["endpoint"],
            "p256dh": payload["keys"]["p256dh"],
            "auth": payload["keys"]["auth"],
        }
