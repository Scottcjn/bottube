# SPDX-License-Identifier: MIT


def _auth_headers(api_key):
    return {"X-API-Key": api_key}


def test_update_agent_mood_rejects_array(client, registered_agent):
    r = client.post(
        f"/api/v1/agents/{registered_agent['agent_name']}/mood/update",
        headers=_auth_headers(registered_agent["api_key"]),
        json=[1, 2],
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "JSON body must be an object"


def test_update_agent_mood_rejects_string(client, registered_agent):
    r = client.post(
        f"/api/v1/agents/{registered_agent['agent_name']}/mood/update",
        headers=_auth_headers(registered_agent["api_key"]),
        json="bad",
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "JSON body must be an object"


def test_record_mood_signal_rejects_number(client, registered_agent):
    r = client.post(
        f"/api/v1/agents/{registered_agent['agent_name']}/mood/signal",
        headers=_auth_headers(registered_agent["api_key"]),
        json=42,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "JSON body must be an object"


def test_pi_approve_rejects_array(client):
    r = client.post("/pi/approve", json=[], headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 503)
    if r.status_code == 400:
        assert r.get_json()["error"] == "JSON body must be an object"


def test_pi_complete_rejects_string(client):
    r = client.post("/pi/complete", json="nope", headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 503)
    if r.status_code == 400:
        assert r.get_json()["error"] == "JSON body must be an object"
