# SPDX-License-Identifier: MIT
import json
import sqlite3
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import x402_payment


@pytest.fixture(autouse=True)
def clear_payment_cache(tmp_path, monkeypatch):
    # Consumed payments are now recorded durably in SQLite, so every test gets
    # its own empty replay store (otherwise rows would leak between tests and
    # into the checkout's bottube.db).
    monkeypatch.setattr(x402_payment, "_REPLAY_DB_PATH", tmp_path / "x402.db")
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
    ("network", "expected"),
    [
        ("eip155:8453", "base"),
        (" EIP155:8453 ", "base"),
        ("base", "base"),
        ("eip155:1", "ethereum"),
        # Networks without an RPC/contract are passed through unchanged and
        # rejected later by _supported_networks(); nothing new is advertised.
        ("eip155:84532", "eip155:84532"),
    ],
)
def test_parse_payment_receipt_normalizes_caip2_network(network, expected):
    receipt = json.dumps({"tx_hash": "0x" + ("ab" * 32), "network": network})
    assert x402_payment._parse_payment_receipt(receipt)["network"] == expected


def test_supported_networks_only_lists_networks_with_rpc():
    for network in x402_payment._supported_networks():
        assert x402_payment.NETWORK_RPCS.get(network)
        assert x402_payment.USDC_CONTRACTS.get(network)


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


# -- Durable replay lock --

FP_SEARCH = "GET:/x402/api/search?q=retro"
FP_VIDEOS = "GET:/x402/api/videos"


def _receipt(tx_hash):
    return json.dumps(
        {
            "tx_hash": tx_hash,
            "network": "base",
            "recipient": x402_payment.USDC_RECEIVING_ADDRESS,
            "amount": "0.000100",
        }
    )


def _fake_chain(monkeypatch, calls=None, err=None):
    def fake_verify(tx_hash_arg, network, recipient):
        if calls is not None:
            calls.append(tx_hash_arg)
        if err:
            return None, err
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


def _verify(tx_hash, fingerprint):
    return x402_payment._verify_payment(
        _receipt(tx_hash), 0.0001, request_fingerprint=fingerprint
    )


def _stored_rows():
    with sqlite3.connect(x402_payment._replay_db_path()) as conn:
        return conn.execute(
            "SELECT tx_hash, network, fingerprint, amount_raw "
            "FROM x402_consumed_payments ORDER BY tx_hash"
        ).fetchall()


def test_replay_after_cache_ttl_eviction_is_rejected(monkeypatch):
    tx_hash = "0x" + ("44" * 32)
    _fake_chain(monkeypatch)

    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "verified")

    # Age the in-memory entry past CACHE_TTL and let cleanup evict it.
    x402_payment._payment_cache[tx_hash]["time"] -= x402_payment.CACHE_TTL + 1
    x402_payment._cleanup_payment_cache()
    assert tx_hash not in x402_payment._payment_cache

    assert _verify(tx_hash, FP_VIDEOS) == (False, "payment_already_consumed", None)
    assert _stored_rows() == [(tx_hash, "base", FP_SEARCH, 100)]


def test_replay_from_another_worker_is_rejected(monkeypatch):
    tx_hash = "0x" + ("55" * 32)
    calls = []
    _fake_chain(monkeypatch, calls)

    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "verified")

    # A different gunicorn worker (or a restarted one) has an empty cache.
    x402_payment._payment_cache.clear()

    assert _verify(tx_hash, FP_VIDEOS) == (False, "payment_already_consumed", None)
    assert calls == [tx_hash]  # rejected from the store, no second RPC


def test_same_fingerprint_retry_still_ok_without_cache(monkeypatch):
    tx_hash = "0x" + ("66" * 32)
    calls = []
    _fake_chain(monkeypatch, calls)

    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "verified")
    x402_payment._payment_cache.clear()

    verified, reason, payment = _verify(tx_hash, FP_SEARCH)
    assert (verified, reason) == (True, "cached")
    assert payment["tx_hash"] == tx_hash
    assert payment["network"] == "base"
    assert payment["amount_raw"] == 100
    assert calls == [tx_hash]
    assert len(_stored_rows()) == 1


def test_recased_tx_hash_is_the_same_payment(monkeypatch):
    tx_hash = "0x" + ("ab" * 32)
    _fake_chain(monkeypatch)

    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "verified")
    x402_payment._payment_cache.clear()

    recased = "0x" + ("AB" * 32)
    assert _verify(recased, FP_VIDEOS) == (False, "payment_already_consumed", None)
    assert len(_stored_rows()) == 1


def test_failed_verification_is_never_recorded(monkeypatch):
    tx_hash = "0x" + ("77" * 32)
    _fake_chain(monkeypatch, err="tx_not_found")

    assert _verify(tx_hash, FP_SEARCH) == (False, "tx_not_found", None)
    assert _stored_rows() == []
    assert tx_hash not in x402_payment._payment_cache

    # Once the transfer is really there, the same hash can still be used.
    _fake_chain(monkeypatch)
    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "verified")


def test_replay_store_failure_fails_closed(monkeypatch, tmp_path):
    tx_hash = "0x" + ("88" * 32)
    _fake_chain(monkeypatch)
    monkeypatch.setattr(
        x402_payment, "_REPLAY_DB_PATH", tmp_path / "missing-dir" / "x402.db"
    )

    assert _verify(tx_hash, FP_SEARCH) == (False, "replay_store_unavailable", None)
    assert tx_hash not in x402_payment._payment_cache


def test_concurrent_claims_have_exactly_one_winner():
    tx_hash = "0x" + ("99" * 32)
    workers = 16
    barrier = threading.Barrier(workers)
    results = [None] * workers

    def claim(i):
        barrier.wait()
        results[i] = x402_payment._claim_payment(
            tx_hash, "base", f"GET:/x402/api/videos?page={i}", 100
        )

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1
    assert results.count(False) == workers - 1
    rows = _stored_rows()
    assert len(rows) == 1
    assert rows[0][2] == f"GET:/x402/api/videos?page={results.index(True)}"


def test_concurrent_verify_of_one_payment_serves_one_endpoint(monkeypatch):
    tx_hash = "0x" + ("aa" * 32)
    _fake_chain(monkeypatch)
    # Every thread behaves like a separate worker: no shared fast path.
    monkeypatch.setattr(x402_payment, "_payment_cache", {})
    workers = 12
    barrier = threading.Barrier(workers)
    results = [None] * workers

    def run(i):
        barrier.wait()
        results[i] = x402_payment._verify_payment(
            _receipt(tx_hash),
            0.0001,
            request_fingerprint=f"GET:/x402/api/videos?page={i}",
        )

    threads = [threading.Thread(target=run, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(1 for r in results if r[0]) == 1
    assert all(
        r == (False, "payment_already_consumed", None) for r in results if not r[0]
    )
    assert len(_stored_rows()) == 1


# -- Same-request retry window (CACHE_TTL) --


def _clock(monkeypatch, start=1_000_000.0):
    now = {"t": start}
    monkeypatch.setattr(x402_payment.time, "time", lambda: now["t"])
    return now


def test_same_fingerprint_retry_within_ttl_ok(monkeypatch):
    tx_hash = "0x" + ("b1" * 32)
    _fake_chain(monkeypatch)
    now = _clock(monkeypatch)

    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "verified")

    now["t"] += x402_payment.CACHE_TTL - 1
    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "cached")  # fast path
    x402_payment._payment_cache.clear()
    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "cached")  # durable path


@pytest.mark.parametrize("clear_cache", [False, True])
def test_same_fingerprint_retry_after_ttl_rejected(monkeypatch, clear_cache):
    tx_hash = "0x" + ("b2" * 32)
    calls = []
    _fake_chain(monkeypatch, calls)
    now = _clock(monkeypatch)

    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "verified")

    now["t"] += x402_payment.CACHE_TTL
    if clear_cache:
        x402_payment._payment_cache.clear()
    assert _verify(tx_hash, FP_SEARCH) == (False, "payment_already_consumed", None)
    # Still rejected much later, and the row is kept forever.
    now["t"] += 30 * 86400
    assert _verify(tx_hash, FP_SEARCH) == (False, "payment_already_consumed", None)
    assert calls == [tx_hash]
    assert _stored_rows() == [(tx_hash, "base", FP_SEARCH, 100)]


def test_cache_refill_does_not_restart_retry_window(monkeypatch):
    tx_hash = "0x" + ("b3" * 32)
    _fake_chain(monkeypatch)
    now = _clock(monkeypatch)

    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "verified")
    now["t"] += x402_payment.CACHE_TTL - 10
    x402_payment._payment_cache.clear()
    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "cached")  # refills cache

    now["t"] += 20  # past TTL since payment, only 20s since the refill
    assert _verify(tx_hash, FP_SEARCH) == (False, "payment_already_consumed", None)


@pytest.mark.parametrize("elapsed", [0, 1800, 3600, 30 * 86400])
@pytest.mark.parametrize("clear_cache", [False, True])
def test_different_fingerprint_rejected_always(monkeypatch, elapsed, clear_cache):
    tx_hash = "0x" + ("b4" * 32)
    _fake_chain(monkeypatch)
    now = _clock(monkeypatch)

    assert _verify(tx_hash, FP_SEARCH)[0:2] == (True, "verified")
    now["t"] += elapsed
    if clear_cache:
        x402_payment._payment_cache.clear()
    assert _verify(tx_hash, FP_VIDEOS) == (False, "payment_already_consumed", None)
