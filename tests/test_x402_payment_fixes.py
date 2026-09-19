# SPDX-License-Identifier: MIT
"""
Hermetic Unit and Integration Test Suite for BoTTube x402 Payment Fixes.

Verifies:
1. maxAmountRequired for 0.01 USDC price is 10000 atomic units (not 10,000,000,000).
2. FACILITATOR_URL configuration is valid and non-NXDOMAIN (falls back from x402-facilitator.cdp.coinbase.com).
3. Network identifier matching (eip155:8453 vs base) works seamlessly in /api/x402/info and payment payload validation.
4. Auth headers (X-API-Key and Authorization: Bearer <key>) both pass authentication on agent wallet endpoints.

Hermetic & fast (< 2 seconds execution time).
"""

import json
import sqlite3
import pytest
from flask import Flask, request

from bottube_x402 import init_app, _extract_api_key, _get_facilitator_url
from x402_payment import (
    _usdc_amount_to_atomic,
    _amount_to_raw,
    _normalize_network,
    _supported_networks,
    _verify_payment,
    _parse_payment_receipt,
    require_payment,
    USDC_RECEIVING_ADDRESS,
    _payment_cache,
)


@pytest.fixture(autouse=True)
def reset_payment_cache():
    """Ensure clean state isolation for payment cache between tests."""
    _payment_cache.clear()
    yield
    _payment_cache.clear()


@pytest.fixture
def app_with_db(tmp_path):
    """Fixture producing a test Flask app initialized with a clean SQLite DB."""
    db_path = tmp_path / "test_bottube.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT UNIQUE NOT NULL,
            display_name TEXT,
            api_key TEXT UNIQUE,
            bio TEXT,
            is_human INTEGER DEFAULT 0,
            coinbase_address TEXT DEFAULT NULL,
            coinbase_wallet_created INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        INSERT INTO agents (agent_name, display_name, api_key)
        VALUES ('test_agent', 'Test Agent', 'test-secret-api-key-123')
    """)
    conn.commit()
    conn.close()

    app = Flask(__name__)
    app.config["TESTING"] = True
    init_app(app, db_path)
    return app


# ==============================================================================
# 1. maxAmountRequired Tests (0.01 USDC -> 10000 atomic units)
# ==============================================================================

class TestMaxAmountRequired:
    """Verify maxAmountRequired calculations for 0.01 USDC and other prices."""

    def test_usdc_amount_to_atomic_0_01_is_10000(self):
        """0.01 USDC must calculate to 10000 atomic units, not 10,000,000,000."""
        assert _usdc_amount_to_atomic(0.01) == "10000"
        assert _usdc_amount_to_atomic("0.01") == "10000"
        assert _amount_to_raw(0.01) == 10000
        assert _amount_to_raw("0.01") == 10000

        # Explicitly verify it is NOT 10^10 (1e6x inflation bug)
        assert _usdc_amount_to_atomic(0.01) != "10000000000"
        assert _amount_to_raw(0.01) != 10000000000

    def test_usdc_amount_to_atomic_other_pricing_tiers(self):
        """Verify atomic unit conversions for standard platform pricing tiers."""
        assert _usdc_amount_to_atomic(0.0001) == "100"       # video_list / search
        assert _usdc_amount_to_atomic(0.0005) == "500"       # video_detail
        assert _usdc_amount_to_atomic(0.001) == "1000"       # video_stream
        assert _usdc_amount_to_atomic(1.0) == "1000000"      # 1.00 USDC

    def test_http_402_body_max_amount_required_0_01_usdc(self):
        """Verify 402 Payment Required response specifies maxAmountRequired: '10000' for 0.01 USDC."""
        app = Flask(__name__)

        @app.route("/test-video-generate")
        @require_payment("video_generate")
        def generate_endpoint():
            return "ok"

        client = app.test_client()
        resp = client.get("/test-video-generate")
        assert resp.status_code == 402
        body = resp.get_json()

        assert body["error"] == "payment_required"
        assert body["payment"]["amount"] == "0.01"
        assert body["payment"]["maxAmountRequired"] == "10000"
        assert body["payment"]["currency"] == "USDC"


# ==============================================================================
# 2. FACILITATOR_URL Configuration Tests
# ==============================================================================

class TestFacilitatorUrl:
    """Verify FACILITATOR_URL configuration is valid and non-NXDOMAIN."""

    def test_default_facilitator_url_is_valid_and_non_nxdomain(self, monkeypatch):
        """Default facilitator URL must be valid and avoid NXDOMAIN domain."""
        monkeypatch.delenv("FACILITATOR_URL", raising=False)
        url = _get_facilitator_url()
        assert url.startswith(("http://", "https://"))
        assert "x402-facilitator.cdp.coinbase.com" not in url
        assert url == "https://www.x402.org/facilitator"

    def test_nxdomain_facilitator_url_overridden(self, monkeypatch):
        """If FACILITATOR_URL is configured to the broken NXDOMAIN endpoint, fall back to default."""
        monkeypatch.setenv("FACILITATOR_URL", "https://x402-facilitator.cdp.coinbase.com/v1")
        url = _get_facilitator_url()
        assert "x402-facilitator.cdp.coinbase.com" not in url
        assert url == "https://www.x402.org/facilitator"

    def test_valid_custom_facilitator_url_accepted(self, monkeypatch):
        """A valid custom facilitator URL should be preserved."""
        custom_url = "https://custom-facilitator.example.com/api"
        monkeypatch.setenv("FACILITATOR_URL", custom_url)
        assert _get_facilitator_url() == custom_url

    def test_x402_info_endpoint_returns_valid_facilitator(self, app_with_db):
        """The /api/x402/info endpoint must return a valid, non-NXDOMAIN facilitator URL."""
        client = app_with_db.test_client()
        resp = client.get("/api/x402/info")
        assert resp.status_code == 200
        body = resp.get_json()

        assert "facilitator" in body
        assert body["facilitator"].startswith(("http://", "https://"))
        assert "x402-facilitator.cdp.coinbase.com" not in body["facilitator"]


# ==============================================================================
# 3. Network Identifier Matching Tests (eip155:8453 vs base)
# ==============================================================================

class TestNetworkIdentifierMatching:
    """Verify seamless matching between eip155:8453 and base network formats."""

    def test_normalize_network_caip2_and_short_names(self):
        """_normalize_network maps CAIP-2 and short names to canonical short representations."""
        assert _normalize_network("eip155:8453") == "base"
        assert _normalize_network("base") == "base"
        assert _normalize_network("eip155:84532") == "base-sepolia"
        assert _normalize_network("eip155:1") == "ethereum"
        assert _normalize_network("EIP155:8453") == "base"
        assert _normalize_network("BASE") == "base"

    def test_supported_networks_contains_caip2_and_short(self):
        """_supported_networks includes both CAIP-2 and short name identifiers."""
        supported = _supported_networks()
        assert "base" in supported
        assert "eip155:8453" in supported
        assert "base-sepolia" in supported
        assert "eip155:84532" in supported

    def test_x402_info_endpoint_network_fields(self, app_with_db):
        """/api/x402/info provides both network (CAIP-2) and network_name (short name)."""
        client = app_with_db.test_client()
        resp = client.get("/api/x402/info")
        assert resp.status_code == 200
        body = resp.get_json()

        assert body["network"] in ("eip155:8453", "eip155:84532")
        assert body["network_name"] in ("base", "base-sepolia")

    def test_payment_payload_validation_supports_eip155_8453_and_base(self, monkeypatch):
        """Payment receipts with network set to eip155:8453 or base both pass validation."""
        tx_hash = "0x" + ("a1" * 32)

        def mock_evm_verify(tx_hash_arg, network, recipient):
            return {
                "tx_hash": tx_hash_arg,
                "network": network,
                "recipient": recipient,
                "from_addresses": ["0x123"],
                "amount_raw": 10000,
                "amount_usdc": 0.01,
                "block_number": 9999,
            }, None

        monkeypatch.setattr("x402_payment._verify_evm_usdc_transfer", mock_evm_verify)

        # 1. Receipt specifying eip155:8453
        receipt_caip2 = json.dumps({
            "tx_hash": tx_hash,
            "network": "eip155:8453",
            "recipient": USDC_RECEIVING_ADDRESS,
            "amount": "0.01",
        })
        ok1, reason1, payment1 = _verify_payment(
            receipt_caip2,
            0.01,
            request_fingerprint="GET:/api/premium/videos",
        )
        assert ok1 is True
        assert reason1 == "verified"
        assert payment1["network"] == "base"

        # Clear cache to test "base" network receipt
        _payment_cache.clear()

        # 2. Receipt specifying short name "base"
        receipt_short = json.dumps({
            "tx_hash": tx_hash,
            "network": "base",
            "recipient": USDC_RECEIVING_ADDRESS,
            "amount": "0.01",
        })
        ok2, reason2, payment2 = _verify_payment(
            receipt_short,
            0.01,
            request_fingerprint="GET:/api/premium/videos",
        )
        assert ok2 is True
        assert reason2 == "verified"
        assert payment2["network"] == "base"


# ==============================================================================
# 4. Auth Headers Tests (X-API-Key and Authorization: Bearer <key>)
# ==============================================================================

class TestAuthHeaders:
    """Verify authentication via X-API-Key and Authorization: Bearer headers."""

    def test_extract_api_key_helper(self, app_with_db):
        """_extract_api_key handles X-API-Key, Bearer token, and raw Authorization header."""
        with app_with_db.test_request_context(headers={"X-API-Key": "key-x-123"}):
            assert _extract_api_key(request) == "key-x-123"

        with app_with_db.test_request_context(headers={"Authorization": "Bearer key-bearer-456"}):
            assert _extract_api_key(request) == "key-bearer-456"

        with app_with_db.test_request_context(headers={"Authorization": "key-raw-789"}):
            assert _extract_api_key(request) == "key-raw-789"

        with app_with_db.test_request_context(headers={"X-API-Key": "key-x-123", "Authorization": "Bearer key-bearer-456"}):
            # X-API-Key takes precedence
            assert _extract_api_key(request) == "key-x-123"

        with app_with_db.test_request_context(headers={}):
            assert _extract_api_key(request) == ""

    def test_agent_wallet_get_with_both_auth_headers(self, app_with_db):
        """GET /api/agents/me/coinbase-wallet succeeds with either X-API-Key or Bearer token."""
        client = app_with_db.test_client()

        # 1. Using X-API-Key header
        resp1 = client.get(
            "/api/agents/me/coinbase-wallet",
            headers={"X-API-Key": "test-secret-api-key-123"},
        )
        assert resp1.status_code == 200
        body1 = resp1.get_json()
        assert body1["agent"] == "test_agent"

        # 2. Using Authorization: Bearer header
        resp2 = client.get(
            "/api/agents/me/coinbase-wallet",
            headers={"Authorization": "Bearer test-secret-api-key-123"},
        )
        assert resp2.status_code == 200
        body2 = resp2.get_json()
        assert body2["agent"] == "test_agent"

        # 3. Invalid API key fails
        resp3 = client.get(
            "/api/agents/me/coinbase-wallet",
            headers={"X-API-Key": "invalid-key"},
        )
        assert resp3.status_code == 401

        # 4. Missing API key fails
        resp4 = client.get("/api/agents/me/coinbase-wallet")
        assert resp4.status_code == 401

    def test_agent_wallet_post_with_both_auth_headers(self, app_with_db):
        """POST /api/agents/me/coinbase-wallet succeeds with either X-API-Key or Bearer token."""
        client = app_with_db.test_client()
        valid_eth_addr1 = "0x1111111111111111111111111111111111111111"
        valid_eth_addr2 = "0x2222222222222222222222222222222222222222"

        # 1. Using X-API-Key header
        resp1 = client.post(
            "/api/agents/me/coinbase-wallet",
            headers={"X-API-Key": "test-secret-api-key-123"},
            json={"coinbase_address": valid_eth_addr1},
        )
        assert resp1.status_code == 200
        body1 = resp1.get_json()
        assert body1["ok"] is True
        assert body1["coinbase_address"] == valid_eth_addr1

        # 2. Using Authorization: Bearer header
        resp2 = client.post(
            "/api/agents/me/coinbase-wallet",
            headers={"Authorization": "Bearer test-secret-api-key-123"},
            json={"coinbase_address": valid_eth_addr2},
        )
        assert resp2.status_code == 200
        body2 = resp2.get_json()
        assert body2["ok"] is True
        assert body2["coinbase_address"] == valid_eth_addr2

    def test_payment_history_get_with_both_auth_headers(self, app_with_db):
        """GET /api/x402/payments returns detailed history with either auth header."""
        client = app_with_db.test_client()

        # X-API-Key
        resp1 = client.get(
            "/api/x402/payments",
            headers={"X-API-Key": "test-secret-api-key-123"},
        )
        assert resp1.status_code == 200
        assert "payments" in resp1.get_json()

        # Authorization: Bearer
        resp2 = client.get(
            "/api/x402/payments",
            headers={"Authorization": "Bearer test-secret-api-key-123"},
        )
        assert resp2.status_code == 200
        assert "payments" in resp2.get_json()
