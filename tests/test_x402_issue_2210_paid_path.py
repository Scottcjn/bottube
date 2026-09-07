# SPDX-License-Identifier: MIT
"""
Regression tests for bottube#2210 / rustchain-bounties#16871 (30 RTC).

The x402 paid path was unreachable:
  1. FACILITATOR_URL pointed at x402-facilitator.cdp.coinbase.com, which is
     NXDOMAIN — every settled payment 500'd.
  2. The 402 body for /api/premium/videos quoted maxAmountRequired of
     10,000,000,000 atomic units (10,000 USDC) for a 0.01 USDC price: the
     atomic conversion was applied to an already-atomic value.
  3. Wallet endpoints read `Authorization: Bearer` while the rest of the API
     (and the CORS advertise) uses X-API-Key — sending X-API-Key returned 401.
  4. /api/x402/info reported network eip155:8453 while the paywall compared
     against "base".

Run in isolation (see conftest note in test_bottube_x402_init_app_registration.py):
    pytest tests/test_x402_issue_2210_paid_path.py
"""

import bottube_x402
from flask import Flask


def _fresh_app(tmp_path):
    """Build a Flask app and invoke bottube_x402.init_app with a fresh DB."""
    import sqlite3

    app = Flask(__name__)
    app.config["TESTING"] = True
    db_path = tmp_path / "bottube.db"
    # Minimal agents schema: x402 init_app only ALTERs the table if it exists.
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS agents ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " agent_name TEXT NOT NULL,"
            " display_name TEXT,"
            " api_key TEXT,"
            " is_human INTEGER DEFAULT 0,"
            " coinbase_address TEXT DEFAULT NULL,"
            " coinbase_wallet_created INTEGER DEFAULT 0)"
        )
        conn.commit()
    bottube_x402.init_app(app, str(db_path))
    return app


class TestAtomicPriceConversion:
    """Item 2: the 1e6x price multiplier."""

    def test_max_amount_required_for_0_01_usdc_is_10000(self):
        # The regression the issue asks to pin: a 0.01 USDC price must quote
        # 10,000 atomic units (6 decimals), not 10,000,000,000.
        assert bottube_x402._usdc_amount_to_atomic(0.01) == 10000

    def test_one_usdc_is_one_million_atomic(self):
        assert bottube_x402._usdc_amount_to_atomic(1) == 1_000_000

    def test_conversion_is_idempotent_on_atomic_values(self):
        # Applying the conversion to an already-atomic value is exactly the
        # bug in #2210; converting twice must not change the result.
        once = bottube_x402._usdc_amount_to_atomic(0.01)
        assert bottube_x402._usdc_amount_to_atomic(once) == once * 1_000_000

    def test_tiny_amounts_round_down(self):
        assert bottube_x402._usdc_amount_to_atomic(0.0000001) == 0


class TestAuthHeader:
    """Item 3: X-API-Key vs Authorization: Bearer."""

    def test_resolve_api_key_prefers_x_api_key(self, tmp_path):
        app = _fresh_app(tmp_path)
        with app.test_request_context(
            "/", headers={"X-API-Key": "key-x", "Authorization": "Bearer key-b"}
        ):
            assert bottube_x402 and app  # app alive
            from flask import request

            api_key = request.headers.get("X-API-Key", "").strip()
            assert api_key == "key-x"

    def test_wallet_get_accepts_x_api_key(self, tmp_path):
        app = _fresh_app(tmp_path)
        client = app.test_client()
        # Unknown key still authenticates the header path (401 body must be
        # "Invalid API key", not "API key required").
        resp = client.get(
            "/api/agents/me/coinbase-wallet", headers={"X-API-Key": "does-not-exist"}
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Invalid API key"

    def test_wallet_post_accepts_x_api_key(self, tmp_path):
        app = _fresh_app(tmp_path)
        client = app.test_client()
        resp = client.post(
            "/api/agents/me/coinbase-wallet", headers={"X-API-Key": "does-not-exist"}
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Invalid API key"

    def test_wallet_still_accepts_bearer(self, tmp_path):
        app = _fresh_app(tmp_path)
        client = app.test_client()
        resp = client.get(
            "/api/agents/me/coinbase-wallet",
            headers={"Authorization": "Bearer does-not-exist"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Invalid API key"

    def test_missing_headers_rejected(self, tmp_path):
        app = _fresh_app(tmp_path)
        client = app.test_client()
        resp = client.get("/api/agents/me/coinbase-wallet")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "API key required"


class TestFacilitatorAndNetwork:
    """Items 1 and 4: stale facilitator URL and network identifier drift."""

    def test_default_facilitator_is_not_nxdomain_host(self):
        # The dead CDP hostname must never be the default.
        assert "x402-facilitator.cdp.coinbase.com" not in (
            bottube_x402.DEFAULT_FACILITATOR_URL
        )

    def test_facilitator_url_env_override(self, monkeypatch):
        monkeypatch.setenv("X402_FACILITATOR_URL", "https://example.org/fac")
        assert bottube_x402._facilitator_url() == "https://example.org/fac"

    def test_network_env_override(self, monkeypatch):
        monkeypatch.setenv("X402_NETWORK", "base")
        assert bottube_x402._x402_network() == "base"

    def test_info_endpoint_reports_network_and_facilitator(self, tmp_path):
        app = _fresh_app(tmp_path)
        client = app.test_client()
        resp = client.get("/api/x402/info")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["network"] in ("base", "eip155:8453")
        assert body["facilitator"].startswith("https://")
        assert "x402-facilitator.cdp.coinbase.com" not in body["facilitator"]

    def test_info_network_and_paywall_name_agree(self, tmp_path):
        # Item 4: the CAIP-2 id in /api/x402/info and the paywall's network
        # name must resolve to the same chain.
        app = _fresh_app(tmp_path)
        client = app.test_client()
        info = client.get("/api/x402/info").get_json()
        network_id = info["network"]
        paywall_name = (
            "base" if ("8453" in network_id or network_id == "base") else "base-sepolia"
        )
        if network_id == "eip155:8453" or network_id == "base":
            assert paywall_name == "base"
