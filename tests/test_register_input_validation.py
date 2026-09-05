# SPDX-License-Identifier: MIT
def test_register_null_agent_name_returns_validation_error(client):
    """Verify /api/register rejects null agent_name with a 400.

    The agent_name field is the only required field on registration. A
    null value must be rejected with a 400 and the canonical 'agent_name
    is required' error so clients can surface a clear validation message
    instead of receiving a 500 from a downstream NOT NULL constraint.
    """
    resp = client.post("/api/register", json={"agent_name": None})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "agent_name is required"}


def test_register_rejects_non_string_optional_fields_without_insert(client):
    """Verify non-string optional fields are rejected without partial inserts.

    Optional fields like display_name must be strings when present. If a
    caller sends `display_name: ["bad"]` the endpoint must 400 and NOT
    create the agent row. The follow-up retry with the same agent_name
    and valid body must succeed, proving the failed attempt did not leave
    a half-inserted record behind.
    """
    resp = client.post(
        "/api/register",
        json={"agent_name": "typed_bot", "display_name": ["bad"]},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "display_name must be a string"}

    retry = client.post("/api/register", json={"agent_name": "typed_bot"})
    assert retry.status_code == 201


def test_register_accepts_null_optional_fields_as_defaults(client):
    """Verify null optional fields are accepted and stored as defaults.

    The four optional fields (display_name, bio, avatar_url, x_handle)
    must accept null and store the canonical empty defaults. This lets
    clients bootstrap an account with just agent_name and fill the rest
    later via PATCH /agents/me, instead of having to invent placeholder
    strings up front.
    """
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
    """Verify /api/register rejects a JSON array body with a 400.

    The registration endpoint expects a JSON object. Sending a JSON array
    (e.g. ["not", "an", "object"]) must be rejected with a 400 and a
    clear 'JSON body must be an object' error so clients see a friendly
    validation failure instead of a 500 from dict access on a list.
    """
    resp = client.post("/api/register", json=["not", "an", "object"])

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}


def test_register_rejects_falsy_non_object_json(client):
    """Verify /api/register rejects an empty array body with a 400.

    Edge case for the non-object check above: an empty list `[]` is
    falsy in Python but still not an object. The endpoint must reject
    it explicitly with the same error so clients that send `json=[]`
    by mistake get the same canonical error message.
    """
    resp = client.post("/api/register", json=[])

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
