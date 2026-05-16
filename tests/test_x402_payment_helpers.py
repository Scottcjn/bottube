import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import x402_payment


@pytest.fixture(autouse=True)
def clear_payment_cache():
    x402_payment._payment_cache.clear()
    yield
    x402_payment._payment_cache.clear()


def test_amount_to_raw_uses_usdc_decimals_and_rounds_down():
    assert x402_payment._amount_to_raw("0") == 0
    assert x402_payment._amount_to_raw("0.000001") == 1
    assert x402_payment._amount_to_raw("0.0000019") == 1
    assert x402_payment._amount_to_raw("1.2345678") == 1_234_567


def test_parse_payment_receipt_defaults_network_and_normalizes_fields():
    tx_hash = "0x" + ("ab" * 32)
    receipt = json.dumps(
        {
            "tx_hash": f"  {tx_hash}  ",
            "recipient": f"  {x402_payment.USDC_RECEIVING_ADDRESS.upper()}  ",
            "amount": "0.0000019",
        }
    )

    parsed = x402_payment._parse_payment_receipt(receipt)

    assert parsed == {
        "tx_hash": tx_hash,
        "network": "base",
        "recipient": x402_payment.USDC_RECEIVING_ADDRESS.lower(),
        "amount_raw": 1,
    }


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ("", "invalid_payment_format"),
        ("  0x" + ("aa" * 32), "invalid_payment_format"),
        (json.dumps(["not", "a", "dict"]), "invalid_payment_format"),
        (json.dumps({"tx_hash": "0xabc", "amount": "not-a-number"}), "invalid_amount"),
    ],
)
def test_parse_payment_receipt_rejects_invalid_payloads(payload, reason):
    with pytest.raises(ValueError, match=reason):
        x402_payment._parse_payment_receipt(payload)


def test_cleanup_payment_cache_removes_expired_entries_only():
    x402_payment._payment_cache.update(
        {
            "expired": {"time": 100, "fingerprint": "GET:/expired"},
            "fresh": {"time": 101, "fingerprint": "GET:/fresh"},
        }
    )

    x402_payment._cleanup_payment_cache(now=100 + x402_payment.CACHE_TTL)

    assert x402_payment._payment_cache == {
        "fresh": {"time": 101, "fingerprint": "GET:/fresh"}
    }


def test_verify_payment_rejects_claimed_underpayment_before_rpc(monkeypatch):
    def fail_if_called(*args, **kwargs):
        pytest.fail("on-chain verifier should not be called for claimed underpayment")

    monkeypatch.setattr(x402_payment, "_verify_evm_usdc_transfer", fail_if_called)

    receipt = json.dumps(
        {
            "tx_hash": "0x" + ("11" * 32),
            "network": "base",
            "recipient": x402_payment.USDC_RECEIVING_ADDRESS,
            "amount": "0.000099",
        }
    )

    verified, reason, payment = x402_payment._verify_payment(
        receipt,
        0.0001,
        request_fingerprint="GET:/x402/api/search?q=retro",
    )

    assert verified is False
    assert reason == "insufficient_amount_claimed"
    assert payment is None


def test_verify_payment_caches_success_and_blocks_cross_endpoint_replay(monkeypatch):
    tx_hash = "0x" + ("22" * 32)
    calls = []

    def fake_verify(tx_hash_arg, network, recipient):
        calls.append((tx_hash_arg, network, recipient))
        return (
            {
                "tx_hash": tx_hash_arg,
                "network": network,
                "recipient": recipient,
                "amount_raw": 100,
                "amount_usdc": 0.0001,
                "block_number": 123,
            },
            None,
        )

    monkeypatch.setattr(x402_payment, "_verify_evm_usdc_transfer", fake_verify)

    receipt = json.dumps(
        {
            "tx_hash": tx_hash,
            "network": "BASE",
            "recipient": x402_payment.USDC_RECEIVING_ADDRESS,
            "amount": "0.000100",
        }
    )

    first = x402_payment._verify_payment(
        receipt,
        0.0001,
        request_fingerprint="GET:/x402/api/search?q=retro",
    )
    second = x402_payment._verify_payment(
        receipt,
        0.0001,
        request_fingerprint="GET:/x402/api/search?q=retro",
    )
    replay = x402_payment._verify_payment(
        receipt,
        0.0001,
        request_fingerprint="GET:/x402/api/videos",
    )

    assert first[0:2] == (True, "verified")
    assert second[0:2] == (True, "cached")
    assert replay == (False, "payment_already_consumed", None)
    assert calls == [
        (tx_hash, "base", x402_payment.USDC_RECEIVING_ADDRESS.lower())
    ]


def test_verify_payment_detects_receipt_and_transfer_amount_mismatch(monkeypatch):
    tx_hash = "0x" + ("33" * 32)

    def fake_verify(tx_hash_arg, network, recipient):
        return (
            {
                "tx_hash": tx_hash_arg,
                "network": network,
                "recipient": recipient,
                "amount_raw": 101,
                "amount_usdc": 0.000101,
                "block_number": 123,
            },
            None,
        )

    monkeypatch.setattr(x402_payment, "_verify_evm_usdc_transfer", fake_verify)

    receipt = json.dumps(
        {
            "tx_hash": tx_hash,
            "network": "base",
            "recipient": x402_payment.USDC_RECEIVING_ADDRESS,
            "amount": "0.000100",
        }
    )

    verified, reason, payment = x402_payment._verify_payment(
        receipt,
        0.0001,
        request_fingerprint="GET:/x402/api/search?q=retro",
    )

    assert verified is False
    assert reason == "amount_mismatch"
    assert payment is None
