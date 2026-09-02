# SPDX-License-Identifier: MIT
"""Input-contract regressions for the Pi authentication endpoint."""

import json


def test_pi_auth_rejects_non_object_json(client):
    response = client.post("/pi/auth", json=["not", "an", "object"])

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON body must be an object"}


def test_pi_auth_rejects_non_string_access_token(client):
    response = client.post("/pi/auth", json={"access_token": 7})

    assert response.status_code == 400
    assert response.get_json() == {"error": "access_token must be a string"}


def test_pi_auth_preserves_required_token_error(client):
    response = client.post("/pi/auth", json={"access_token": "   "})

    assert response.status_code == 400
    assert response.get_json() == {"error": "access_token required"}


def test_pi_auth_preserves_valid_string_flow(client, monkeypatch):
    import bottube_server

    class PiResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"uid": "pi-uid-2075", "username": "pi-tester"}).encode()

    def fake_urlopen(request, timeout):
        assert request.full_url == "https://api.minepi.com/v2/me"
        assert request.headers["Authorization"] == "Bearer valid-token"
        assert timeout == 10
        return PiResponse()

    monkeypatch.setattr(bottube_server.urllib.request, "urlopen", fake_urlopen)

    response = client.post("/pi/auth", json={"access_token": " valid-token "})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "username": "pi-tester", "created": True}
