# SPDX-License-Identifier: MIT
"""
Regression test for Bottube #1340 / Bounty #351.

The BoTTube x402 module (bottube_x402.py) defines 7 endpoints via init_app:
- GET  /api/premium/videos
- GET  /api/premium/analytics/<agent_identifier>
- GET  /api/premium/trending/export
- GET  /api/agents/me/coinbase-wallet
- POST /api/agents/me/coinbase-wallet
- GET  /api/x402/payments
- GET  /api/x402/info

Before the fix, bottube_server.py imported `x402_payment.x402_bp` but never
called `bottube_x402.init_app`, so the 7 endpoints returned 404 from
bottube.ai. This test pins the registration contract so the fix is not
silently regressed.
"""

# This test file MUST be run in isolation, or pytest will collect it
# together with test_x402_payment.py (which stubs sys.modules['flask']
# and breaks subsequent imports of real flask).
# Use: `pytest tests/test_bottube_x402_init_app_registration.py`

import sqlite3

import bottube_x402
from flask import Flask


EXPECTED_ROUTE_PATHS = {
    "/api/premium/videos",
    "/api/premium/analytics/<agent_identifier>",
    "/api/premium/trending/export",
    "/api/agents/me/coinbase-wallet",
    "/api/x402/payments",
    "/api/x402/info",
}


def _fresh_app(tmp_path):
    """Build a Flask app and invoke bottube_x402.init_app with a fresh DB."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    db_path = tmp_path / "bottube.db"
    bottube_x402.init_app(app, str(db_path))
    return app


def test_bottube_x402_init_app_registers_all_routes(tmp_path):
    app = _fresh_app(tmp_path)

    actual = set()
    for rule in app.url_map.iter_rules():
        if (
            "premium" in rule.rule
            or "x402" in rule.rule
            or "coinbase-wallet" in rule.rule
        ):
            actual.add(rule.rule)

    missing = EXPECTED_ROUTE_PATHS - actual
    extra = actual - EXPECTED_ROUTE_PATHS
    assert not missing, f"bottube_x402.init_app did not register: {missing}"
    assert not extra, f"bottube_x402.init_app registered unexpected: {extra}"


def test_bottube_x402_coinbase_wallet_accepts_get_and_post(tmp_path):
    app = _fresh_app(tmp_path)

    # /api/agents/me/coinbase-wallet is registered by Flask as two rules
    # (one per method); aggregate to confirm both GET and POST are present.
    coinbase_methods = set()
    for rule in app.url_map.iter_rules():
        if rule.rule == "/api/agents/me/coinbase-wallet":
            coinbase_methods.update(rule.methods - {"HEAD", "OPTIONS"})
    assert {"GET", "POST"}.issubset(coinbase_methods)


def test_bottube_x402_info_endpoint_responds(tmp_path):
    app = _fresh_app(tmp_path)
    client = app.test_client()

    resp = client.get("/api/x402/info")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body is not None
    assert "x402_enabled" in body
    assert "premium_endpoints" in body
    assert "wallet_endpoints" in body
    # premium_endpoints should list the three premium routes
    paths = {ep["path"] for ep in body["premium_endpoints"]}
    assert "/api/premium/videos" in paths
    assert "/api/premium/analytics/<agent>" in paths
    assert "/api/premium/trending/export" in paths


def test_bottube_x402_payments_endpoint_responds(tmp_path):
    app = _fresh_app(tmp_path)
    client = app.test_client()

    resp = client.get("/api/x402/payments")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body is not None
    # Without an API key, the public summary is returned
    assert "total_payments" in body
    assert "hint" in body


def test_bottube_x402_coinbase_wallet_requires_api_key(tmp_path):
    app = _fresh_app(tmp_path)
    client = app.test_client()

    resp = client.get("/api/agents/me/coinbase-wallet")
    assert resp.status_code == 401
    body = resp.get_json()
    assert body is not None
    assert "error" in body


def _wallet_app(tmp_path):
    with sqlite3.connect(tmp_path / "bottube.db") as conn:
        conn.execute(
            "CREATE TABLE agents (id INTEGER PRIMARY KEY, agent_name TEXT, "
            "display_name TEXT, api_key TEXT)"
        )
        conn.execute(
            "INSERT INTO agents (id, agent_name, display_name, api_key) "
            "VALUES (1, 'tester', 'Tester', 'secret')"
        )
    return _fresh_app(tmp_path)


def test_bottube_x402_coinbase_wallet_rejects_malformed_json(tmp_path, monkeypatch):
    app = _wallet_app(tmp_path)
    client = app.test_client()
    headers = {"Authorization": "Bearer secret"}
    wallet_calls = []

    def create_wallet():
        wallet_calls.append(True)
        return "0x" + "ab" * 20, {}

    monkeypatch.setattr(bottube_x402, "X402_AVAILABLE", True)
    monkeypatch.setattr(bottube_x402, "has_cdp_credentials", lambda: True, raising=False)
    monkeypatch.setattr(bottube_x402, "create_agentkit_wallet", create_wallet, raising=False)
    cases = [
        ("not-object", "JSON body must be an object"),
        (["not", "object"], "JSON body must be an object"),
    ]
    for value in (["0x123"], {"address": "0x123"}, 1, True, 0, False, [], {}):
        cases.append(({"coinbase_address": value}, "coinbase_address must be a string"))
    for payload, expected_error in cases:
        resp = client.post("/api/agents/me/coinbase-wallet", json=payload, headers=headers)
        assert resp.status_code == 400
        assert resp.get_json() == {"error": expected_error}
    assert wallet_calls == []
    with sqlite3.connect(tmp_path / "bottube.db") as conn:
        assert conn.execute(
            "SELECT coinbase_address, coinbase_wallet_created FROM agents WHERE id=1"
        ).fetchone() == (None, 0)


def test_bottube_x402_coinbase_wallet_preserves_string_linking_and_auto_creation(tmp_path, monkeypatch):
    app = _wallet_app(tmp_path)
    client = app.test_client()
    headers = {"X-API-Key": "secret"}
    manual_address = "0x" + "ab" * 20
    resp = client.post(
        "/api/agents/me/coinbase-wallet",
        json={"coinbase_address": manual_address}, headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["method"] == "manual_link"
    assert resp.get_json()["coinbase_address"] == manual_address

    auto_address = "0x" + "cd" * 20
    monkeypatch.setattr(bottube_x402, "X402_AVAILABLE", True)
    monkeypatch.setattr(bottube_x402, "has_cdp_credentials", lambda: True, raising=False)
    monkeypatch.setattr(
        bottube_x402, "create_agentkit_wallet", lambda: (auto_address, {}), raising=False,
    )
    for payload in ({}, {"coinbase_address": None}, {"coinbase_address": ""}):
        resp = client.post("/api/agents/me/coinbase-wallet", json=payload, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["method"] == "agentkit"
        assert resp.get_json()["coinbase_address"] == auto_address
