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


def test_extract_api_key_unit():
    from unittest.mock import MagicMock
    from bottube_x402 import _extract_api_key

    # X-API-Key header
    req1 = MagicMock()
    req1.headers.get.side_effect = lambda k, default=None: "key_x_api" if k == "X-API-Key" else default
    assert _extract_api_key(req1) == "key_x_api"

    # Authorization: Bearer <key>
    req2 = MagicMock()
    req2.headers.get.side_effect = lambda k, default=None: "Bearer key_bearer" if k == "Authorization" else default
    assert _extract_api_key(req2) == "key_bearer"

    # Authorization: bearer <key> (case-insensitive)
    req3 = MagicMock()
    req3.headers.get.side_effect = lambda k, default=None: "bearer key_lower_bearer" if k == "Authorization" else default
    assert _extract_api_key(req3) == "key_lower_bearer"

    # Authorization: <key> (no prefix)
    req4 = MagicMock()
    req4.headers.get.side_effect = lambda k, default=None: "key_raw" if k == "Authorization" else default
    assert _extract_api_key(req4) == "key_raw"

    # Empty X-API-Key falls back to Authorization
    req5 = MagicMock()
    req5.headers.get.side_effect = lambda k, default=None: " " if k == "X-API-Key" else ("Bearer key_fallback" if k == "Authorization" else default)
    assert _extract_api_key(req5) == "key_fallback"


def _app_with_agent(tmp_path):
    import sqlite3
    app = Flask(__name__)
    app.config["TESTING"] = True
    db_path = tmp_path / "bottube.db"

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT UNIQUE NOT NULL,
            display_name TEXT,
            api_key TEXT UNIQUE,
            bio TEXT,
            is_human INTEGER DEFAULT 0,
            coinbase_address TEXT DEFAULT NULL,
            coinbase_wallet_created INTEGER DEFAULT 0
        )""")
        conn.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("testagent", "Test Agent", "valid_secret_key_123"),
        )
        conn.commit()

    bottube_x402.init_app(app, str(db_path))
    return app


def test_x402_auth_header_consistency_wallet_get(tmp_path):
    app = _app_with_agent(tmp_path)
    client = app.test_client()

    # Via X-API-Key
    resp1 = client.get("/api/agents/me/coinbase-wallet", headers={"X-API-Key": "valid_secret_key_123"})
    assert resp1.status_code == 200
    assert resp1.get_json()["agent"] == "testagent"

    # Via Authorization: Bearer
    resp2 = client.get("/api/agents/me/coinbase-wallet", headers={"Authorization": "Bearer valid_secret_key_123"})
    assert resp2.status_code == 200
    assert resp2.get_json()["agent"] == "testagent"

    # Via Authorization: bearer (case-insensitive)
    resp3 = client.get("/api/agents/me/coinbase-wallet", headers={"Authorization": "bearer valid_secret_key_123"})
    assert resp3.status_code == 200
    assert resp3.get_json()["agent"] == "testagent"


def test_x402_auth_header_consistency_wallet_post(tmp_path):
    app = _app_with_agent(tmp_path)
    client = app.test_client()

    payload = {"coinbase_address": "0x1111111111111111111111111111111111111111"}

    # Via X-API-Key
    resp1 = client.post("/api/agents/me/coinbase-wallet", headers={"X-API-Key": "valid_secret_key_123"}, json=payload)
    assert resp1.status_code == 200
    assert resp1.get_json()["ok"] is True

    payload2 = {"coinbase_address": "0x2222222222222222222222222222222222222222"}

    # Via Authorization: Bearer
    resp2 = client.post("/api/agents/me/coinbase-wallet", headers={"Authorization": "Bearer valid_secret_key_123"}, json=payload2)
    assert resp2.status_code == 200
    assert resp2.get_json()["ok"] is True


def test_x402_auth_header_consistency_payments_get(tmp_path):
    app = _app_with_agent(tmp_path)
    client = app.test_client()

    # Via X-API-Key
    resp1 = client.get("/api/x402/payments", headers={"X-API-Key": "valid_secret_key_123"})
    assert resp1.status_code == 200
    assert "payments" in resp1.get_json()

    # Via Authorization: Bearer
    resp2 = client.get("/api/x402/payments", headers={"Authorization": "Bearer valid_secret_key_123"})
    assert resp2.status_code == 200
    assert "payments" in resp2.get_json()
