# SPDX-License-Identifier: MIT
"""Request-contract regressions for the Sophia chat endpoint."""

from flask import Flask

import sophia_blueprint


def _client():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="sophia-contract-test")
    app.register_blueprint(sophia_blueprint.sophia_bp)
    return app.test_client()


def test_malformed_fields_are_rejected_before_authentication_or_inference(monkeypatch):
    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("malformed input reached authentication or inference")

    monkeypatch.setattr(sophia_blueprint, "_resolve_caller", unexpected_call)
    monkeypatch.setattr(sophia_blueprint, "_call_sophia", unexpected_call)
    client = _client()

    cases = [
        (["hello"], "JSON body must be an object"),
        ({"agent_api_key": 42, "message": "hello"}, "agent_api_key must be a string"),
        ({"message": ["hello"]}, "message must be a string"),
        ({"message": 42}, "message must be a string"),
    ]
    for payload, expected_error in cases:
        response = client.post("/api/sophia", json=payload)
        assert response.status_code == 400
        assert response.get_json() == {"error": expected_error}


def test_valid_public_message_preserves_chat_and_cors_behavior(monkeypatch):
    monkeypatch.setattr(sophia_blueprint, "_resolve_caller", lambda body: None)
    monkeypatch.setattr(sophia_blueprint, "_call_sophia", lambda message, history: f"reply:{message}")
    monkeypatch.setattr(sophia_blueprint, "_log_corpus", lambda *_args: None)
    monkeypatch.setattr(sophia_blueprint, "SOPHIA_PUBLIC_CHAT", True)
    monkeypatch.setattr(sophia_blueprint, "_PUBLIC_COOLDOWN", 0)
    sophia_blueprint._ip_rate.clear()
    client = _client()

    response = client.post(
        "/api/sophia",
        json={"message": "  hello Sophia  "},
        headers={"Origin": "https://bottube.ai"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "reply": "reply:hello Sophia",
        "from": "Sophia Elya",
        "caller": "guest",
        "generation": None,
    }
    assert response.headers["Access-Control-Allow-Origin"] == "https://bottube.ai"


def test_options_and_existing_required_message_contract_remain_intact(monkeypatch):
    client = _client()
    preflight = client.options(
        "/api/sophia",
        headers={"Origin": "https://bottube.ai"},
    )
    assert preflight.status_code == 204
    assert preflight.headers["Access-Control-Allow-Origin"] == "https://bottube.ai"

    monkeypatch.setattr(sophia_blueprint, "_resolve_caller", lambda body: None)
    monkeypatch.setattr(sophia_blueprint, "SOPHIA_PUBLIC_CHAT", True)
    response = client.post("/api/sophia", json={"message": "   "})
    assert response.status_code == 400
    assert response.get_json() == {"error": "message required"}
