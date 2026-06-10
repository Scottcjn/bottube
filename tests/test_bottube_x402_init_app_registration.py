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
