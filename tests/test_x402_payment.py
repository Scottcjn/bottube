"""
Unit tests for x402_payment.py — BoTTube x402 payment protocol helpers.

Covers:
  - _amount_to_raw(): USDC amount to raw integer conversion
  - _parse_payment_receipt(): JSON receipt parsing and validation
  - _cleanup_payment_cache(): cache expiry logic
  - _supported_networks(): network listing
  - Edge cases: invalid amounts, malformed JSON, missing fields, negative values
"""

import json
import time

import pytest

# Import the module — patch Flask request context dependencies first
import sys
import types

# Create a minimal Flask stub so the module can be imported without a running app
flask_stub = types.ModuleType("flask")
flask_stub.Blueprint = lambda *a, **kw: types.SimpleNamespace(route=lambda *a, **kw: lambda f: f)
flask_stub.request = types.SimpleNamespace(
    method="GET", full_path="/", headers={}, args={}
)
flask_stub.jsonify = lambda d: d
flask_stub.g = types.SimpleNamespace()
sys.modules.setdefault("flask", flask_stub)

# Stub requests module
requests_stub = types.ModuleType("requests")
requests_stub.post = lambda *a, **kw: None
sys.modules.setdefault("requests", requests_stub)

from x402_payment import (
    _amount_to_raw,
    _parse_payment_receipt,
    _cleanup_payment_cache,
    _supported_networks,
    _payment_cache,
    USDC_DECIMALS,
    CACHE_TTL,
)


class TestAmountToRaw:
    """Tests for _amount_to_raw() — USDC decimal to raw integer."""

    def test_zero_amount(self):
        assert _amount_to_raw(0) == 0

    def test_one_usdc(self):
        # 1 USDC = 1_000_000 raw (6 decimals)
        assert _amount_to_raw(1) == 1_000_000

    def test_small_amount(self):
        # 0.001 USDC = 1000 raw
        assert _amount_to_raw(0.001) == 1000

    def test_very_small_amount(self):
        # 0.000001 USDC = 1 raw (smallest unit)
        assert _amount_to_raw(0.000001) == 1

    def test_string_amount(self):
        # Function accepts string representation
        assert _amount_to_raw("0.01") == 10_000

    def test_large_amount(self):
        # 1000 USDC
        assert _amount_to_raw(1000) == 1_000_000_000

    def test_rounds_down_truncation(self):
        # Amounts with more than 6 decimal places should be truncated (ROUND_DOWN)
        # 0.0000001 USDC = 0.1 raw -> rounds down to 0
        assert _amount_to_raw(0.0000001) == 0

    def test_decimal_type_input(self):
        from decimal import Decimal
        assert _amount_to_raw(Decimal("0.5")) == 500_000


class TestParsePaymentReceipt:
    """Tests for _parse_payment_receipt() — JSON receipt parsing."""

    def test_valid_receipt(self):
        data = json.dumps({
            "tx_hash": "0x" + "ab" * 32,
            "network": "base",
            "recipient": "0xd10A6AbFED84dDD28F89bB3d836BD20D5da8fEBf",
            "amount": 0.001,
        })
        result = _parse_payment_receipt(data)
        assert result["tx_hash"] == "0x" + "ab" * 32
        assert result["network"] == "base"
        assert result["recipient"] == "0xd10a6abfed84ddd28f89bb3d836bd20d5da8febf"
        assert result["amount_raw"] == 1000

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="invalid_payment_format"):
            _parse_payment_receipt("")

    def test_non_json_raises(self):
        with pytest.raises(ValueError, match="invalid_payment_format"):
            _parse_payment_receipt("not json at all")

    def test_non_object_json_raises(self):
        with pytest.raises(ValueError, match="invalid_payment_format"):
            _parse_payment_receipt("[1, 2, 3]")

    def test_missing_tx_hash_defaults_empty(self):
        data = json.dumps({"network": "base", "recipient": "0xabc", "amount": 1})
        result = _parse_payment_receipt(data)
        assert result["tx_hash"] == ""

    def test_missing_amount_defaults_none(self):
        data = json.dumps({
            "tx_hash": "0x" + "ab" * 32,
            "network": "base",
            "recipient": "0xabc",
        })
        result = _parse_payment_receipt(data)
        assert result["amount_raw"] is None

    def test_network_is_lowercased(self):
        data = json.dumps({
            "tx_hash": "0x" + "ab" * 32,
            "network": "BASE",
            "recipient": "0xABC",
        })
        result = _parse_payment_receipt(data)
        assert result["network"] == "base"
        assert result["recipient"] == "0xabc"

    def test_invalid_amount_raises(self):
        data = json.dumps({
            "tx_hash": "0x" + "ab" * 32,
            "network": "base",
            "recipient": "0xabc",
            "amount": "not_a_number",
        })
        with pytest.raises(ValueError, match="invalid_amount"):
            _parse_payment_receipt(data)

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="invalid_payment_format"):
            _parse_payment_receipt("   ")

    def test_json_with_whitespace_prefix(self):
        """JSON with leading whitespace should still parse."""
        data = '  {"tx_hash": "0x' + 'ab' * 32 + '", "network": "base"}'
        result = _parse_payment_receipt(data)
        assert result["network"] == "base"


class TestCleanupPaymentCache:
    """Tests for _cleanup_payment_cache()."""

    def test_removes_expired_entries(self):
        _payment_cache.clear()
        _payment_cache["old_tx"] = {"time": time.time() - CACHE_TTL - 100, "fingerprint": "x"}
        _payment_cache["new_tx"] = {"time": time.time(), "fingerprint": "y"}
        _cleanup_payment_cache()
        assert "old_tx" not in _payment_cache
        assert "new_tx" in _payment_cache
        _payment_cache.clear()

    def test_keeps_fresh_entries(self):
        _payment_cache.clear()
        _payment_cache["fresh"] = {"time": time.time(), "fingerprint": "z"}
        _cleanup_payment_cache()
        assert "fresh" in _payment_cache
        _payment_cache.clear()

    def test_empty_cache_no_error(self):
        _payment_cache.clear()
        _cleanup_payment_cache()  # Should not raise
        assert len(_payment_cache) == 0


class TestSupportedNetworks:
    """Tests for _supported_networks()."""

    def test_returns_list(self):
        result = _supported_networks()
        assert isinstance(result, list)

    def test_base_always_supported(self):
        result = _supported_networks()
        assert "base" in result

    def test_no_empty_strings(self):
        result = _supported_networks()
        for net in result:
            assert net.strip() != "", "Empty string in supported networks"
