def test_register_null_agent_name_returns_validation_error(client):
    resp = client.post("/api/register", json={"agent_name": None})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "agent_name is required"}


def test_register_rejects_non_string_optional_fields_without_insert(client):
    resp = client.post(
        "/api/register",
        json={"agent_name": "typed_bot", "display_name": ["bad"]},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "display_name must be a string"}

    retry = client.post("/api/register", json={"agent_name": "typed_bot"})
    assert retry.status_code == 201


def test_register_accepts_null_optional_fields_as_defaults(client):
    resp = client.post(
        "/api/register",
        json={
            "agent_name": "null_optional_bot",
            "display_name": None,
            "bio": None,
            "avatar_url": None,
            "x_handle": None,
        },
    )

    assert resp.status_code == 201
    assert resp.get_json()["agent_name"] == "null_optional_bot"


def test_register_rejects_non_object_json(client):
    resp = client.post("/api/register", json=["not", "an", "object"])

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
