# SPDX-License-Identifier: MIT
"""
Regression tests for BoTTube Issue #2210:
- Price multiplier 1e6x fix (0.01 USDC quotes maxAmountRequired: "10000")
- X-API-Key header support on agent wallet and payment history endpoints
- Facilitator default fallback (https://www.x402.org/facilitator)
- CAIP-2 network identifier normalization (eip155:8453 and base)
"""

import json
import sqlite3
import pytest
from flask import Flask
from bottube_x402 import init_app, _extract_api_key
from x402_payment import (
    _usdc_amount_to_atomic,
    _amount_to_raw,
    _normalize_network,
    _supported_networks,
    require_payment,
)


def test_usdc_amount_to_atomic_0_01_is_10000():
    """Assert maxAmountRequired for 0.01 USDC is strictly 10000 (fixes 1e6x bug)."""
    assert _usdc_amount_to_atomic(0.01) == "10000"
    assert _usdc_amount_to_atomic("0.01") == "10000"
    assert _usdc_amount_to_atomic("10000") == "10000"
    assert _amount_to_raw(0.01) == 10000
    assert _amount_to_raw("10000") == 10000


def test_require_payment_402_body_includes_max_amount_required():
    """Verify HTTP 402 response includes maxAmountRequired: '10000' for 0.01 USDC."""
    app = Flask(__name__)

    @app.route("/test-paywall")
    @require_payment("video_generate")
    def dummy_route():
        return "ok"

    client = app.test_client()
    resp = client.get("/test-paywall")
    assert resp.status_code == 402
    body = resp.get_json()
    assert body["error"] == "payment_required"
    assert body["payment"]["amount"] == "0.01"
    assert body["payment"]["maxAmountRequired"] == "10000"


def test_network_identifier_normalization():
    """Verify eip155:8453 and base are normalized to base."""
    assert _normalize_network("eip155:8453") == "base"
    assert _normalize_network("base") == "base"
    supported = _supported_networks()
    assert "base" in supported
    assert "eip155:8453" in supported


def test_x_api_key_header_authentication(tmp_path):
    """Verify endpoints accept X-API-Key in addition to Authorization: Bearer."""
    db_path = tmp_path / "bottube.db"
    conn = sqlite3.connect(db_path)
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
    conn.execute("INSERT INTO agents (agent_name, display_name, api_key) VALUES ('testbot', 'Test Bot', 'secret-key-123')")
    conn.commit()
    conn.close()

    app = Flask(__name__)
    app.config["TESTING"] = True
    init_app(app, db_path)
    client = app.test_client()

    # Test GET wallet with X-API-Key
    resp = client.get("/api/agents/me/coinbase-wallet", headers={"X-API-Key": "secret-key-123"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["agent"] == "testbot"

    # Test POST wallet with X-API-Key
    resp = client.post(
        "/api/agents/me/coinbase-wallet",
        headers={"X-API-Key": "secret-key-123"},
        json={"coinbase_address": "0x1234567890123456789012345678901234567890"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["coinbase_address"] == "0x1234567890123456789012345678901234567890"

    # Test payment history with X-API-Key
    resp = client.get("/api/x402/payments", headers={"X-API-Key": "secret-key-123"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert "payments" in body


def test_x402_info_facilitator_and_network_defaults(tmp_path):
    """Verify /api/x402/info returns valid facilitator and eip155:8453 network."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    db_path = tmp_path / "bottube.db"
    init_app(app, db_path)
    client = app.test_client()

    resp = client.get("/api/x402/info")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["network"] in ("eip155:8453", "eip155:84532")
    assert body["network_name"] in ("base", "base-sepolia")
    assert "x402-facilitator.cdp.coinbase.com" not in body["facilitator"]
    assert body["facilitator"] == "https://www.x402.org/facilitator"


def test_real_premium_videos_402_body(tmp_path):
    """Verify real /api/premium/videos route behavior."""
    db_path = tmp_path / "bottube.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT UNIQUE,
        title TEXT,
        description TEXT,
        agent_id INTEGER,
        views INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        dislikes INTEGER DEFAULT 0,
        created_at TEXT,
        duration_sec INTEGER,
        thumbnail TEXT,
        tags TEXT,
        category TEXT,
        is_removed INTEGER DEFAULT 0
    )""")
    conn.commit()
    conn.close()

    app = Flask(__name__)
    app.config["TESTING"] = True
    init_app(app, db_path)
    client = app.test_client()

    resp = client.get("/api/premium/videos")
    assert resp.status_code in (200, 402)
    if resp.status_code == 402:
        body = resp.get_json()
        assert body.get("error") == "payment_required"
        assert body.get("payment", {}).get("maxAmountRequired") == "10000"

