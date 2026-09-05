"""Request-contract regressions for agent terms acceptance."""

from flask import Flask, g

import bottube_server


def _client():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="terms-contract-test")

    @app.before_request
    def _set_agent():
        g.agent = {"id": 17, "agent_name": "contract-test-agent"}

    app.add_url_rule(
        "/api/agents/me/accept-terms",
        "test_agent_accept_terms",
        bottube_server.agent_accept_terms.__wrapped__,
        methods=["POST"],
    )
    return app.test_client()


def test_malformed_terms_bodies_are_rejected_before_mutation(monkeypatch):
    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("malformed input reached the terms mutation edge")

    monkeypatch.setattr(bottube_server, "_ensure_ts_schema", unexpected_call)
    monkeypatch.setattr(bottube_server, "get_db", unexpected_call)
    monkeypatch.setattr(bottube_server, "_ts_log_audit", unexpected_call)
    client = _client()

    cases = [
        (["current"], "Request body must be a JSON object"),
        ({"version": 3}, "version must be a string"),
        ({"version": ["current"]}, "version must be a string"),
    ]
    for payload, expected_error in cases:
        response = client.post("/api/agents/me/accept-terms", json=payload)
        assert response.status_code == 400
        assert response.get_json() == {"error": expected_error}

    null_response = client.post(
        "/api/agents/me/accept-terms", data="null", content_type="application/json"
    )
    assert null_response.status_code == 400
    assert null_response.get_json() == {"error": "Request body must be a JSON object"}


def test_omitted_version_preserves_current_terms_acceptance(monkeypatch):
    operations = []

    class FakeDB:
        def execute(self, sql, params):
            operations.append(("execute", sql, params))
            return self

        def commit(self):
            operations.append(("commit",))

    monkeypatch.setattr(bottube_server, "_ensure_ts_schema", lambda: operations.append(("schema",)))
    monkeypatch.setattr(bottube_server, "get_db", lambda: FakeDB())
    monkeypatch.setattr(
        bottube_server,
        "_ts_log_audit",
        lambda *args, **kwargs: operations.append(("audit", args, kwargs)),
    )

    response = _client().post("/api/agents/me/accept-terms", json={})

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["agent_name"] == "contract-test-agent"
    assert data["tos_version_accepted"] == bottube_server.TOS_VERSION
    assert [entry[0] for entry in operations] == ["schema", "execute", "commit", "audit"]
    assert operations[1][2][0] == bottube_server.TOS_VERSION
