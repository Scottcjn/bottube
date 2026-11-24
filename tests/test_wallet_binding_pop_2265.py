# SPDX-License-Identifier: MIT
"""Security regression tests for wallet proof-of-possession verification (#2265).

Covers:
1. Direct self-asserted wallet binding (`POST /api/agents/me/wallet`) fails closed
   with 403 for deposit-binding chains (`eth`, `sol`, `erg`) without PoP, while
   preserving non-deposit wallet updates and clearing.
2. End-to-end challenge + signature verification + deposit flows for ETH
   (EIP-191 personal_sign via pure-Python Keccak-256 + secp256k1 ecrecover),
   SOL (Ed25519 via PyNaCl), and ERG (P2PK Base58Check + Blake2b-256 ECDSA),
   using ZERO `eth_account` runtime dependency in production code.
3. Replay, expiration, wrong-signer, high-s malleability, cross-agent challenge
   hijacking, and cross-account address claiming rejection.
4. Defense-in-depth across `usdc_blueprint`, `base_wrtc_bridge_blueprint`,
   `wrtc_bridge_blueprint`, `ergo_bridge_blueprint`, and `wrtc_bridge`: legacy or
   directly-seeded unverified `agents.*_address` rows fail with 403 before any
   on-chain RPC lookup or balance credit.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import sys
import time
from importlib import metadata

import nacl.signing
import pytest
import werkzeug
from flask import Flask, g

import base_wrtc_bridge_blueprint as base_bridge
import ergo_bridge_blueprint as ergo_bridge
import usdc_blueprint as usdc
import wallet_verification as wv
import wrtc_bridge as legacy_wrtc
import wrtc_bridge_blueprint as sol_bridge

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


@pytest.fixture()
def client(app, monkeypatch):
    """Ensure blueprints using resolve_db_path() share and initialize the conftest DB."""
    db_path = app.config["DB_PATH"]
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    monkeypatch.setenv("BOTTUBE_DB", str(db_path))
    conn = sqlite3.connect(str(db_path))
    try:
        usdc.init_usdc_tables(conn)
        base_bridge.init_base_wrtc_tables(conn)
        sol_bridge.init_wrtc_tables(conn)
        ergo_bridge.init_ergo_tables(conn)
        conn.commit()
    finally:
        conn.close()
    return app.test_client()

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _encode_base58(raw: bytes) -> str:
    num = int.from_bytes(raw, "big")
    chars = []
    while num:
        num, rem = divmod(num, 58)
        chars.append(_B58[rem])
    leading = 0
    for byte in raw:
        if byte == 0:
            leading += 1
        else:
            break
    return ("1" * leading) + "".join(reversed(chars))


def _make_secp256k1_keypair():
    """Generate a test secp256k1 private scalar and uncompressed point (x, y)."""
    priv = 1 + secrets.randbelow(wv._SECP256K1_N - 1)
    pub = wv._point_mul(priv, wv._SECP256K1_G)
    assert pub is not None
    return priv, pub


def _sign_secp256k1_digest(priv: int, digest32: bytes) -> bytes:
    """Deterministic test ECDSA signer producing canonical low-s 65-byte (r||s||v)."""
    z = int.from_bytes(digest32, "big") % wv._SECP256K1_N
    while True:
        k = 1 + secrets.randbelow(wv._SECP256K1_N - 1)
        R = wv._point_mul(k, wv._SECP256K1_G)
        if R is None:
            continue
        r = R[0] % wv._SECP256K1_N
        if r == 0:
            continue
        s = (pow(k, -1, wv._SECP256K1_N) * (z + r * priv)) % wv._SECP256K1_N
        if s == 0:
            continue
        rec_id = R[1] & 1
        if s > wv._SECP256K1_N // 2:
            s = wv._SECP256K1_N - s
            rec_id ^= 1
        return r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([27 + rec_id])


def _eth_address_from_pub(pub: tuple[int, int]) -> str:
    raw_pub = pub[0].to_bytes(32, "big") + pub[1].to_bytes(32, "big")
    return "0x" + wv.keccak_256(raw_pub)[-20:].hex()


def _sign_eip191(priv: int, message: str) -> str:
    msg_bytes = message.encode("utf-8")
    prefixed = b"\x19Ethereum Signed Message:\n" + str(len(msg_bytes)).encode("ascii") + msg_bytes
    return "0x" + _sign_secp256k1_digest(priv, wv.keccak_256(prefixed)).hex()


def _ergo_address_from_pub(pub: tuple[int, int]) -> str:
    pk33 = wv._compress_secp256k1_pubkey(pub)
    payload = b"\x01" + pk33
    checksum = hashlib.blake2b(payload, digest_size=32).digest()[:4]
    return _encode_base58(payload + checksum)


def _sign_ergo(priv: int, message: str) -> str:
    digest = hashlib.blake2b(message.encode("utf-8"), digest_size=32).digest()
    return "0x" + _sign_secp256k1_digest(priv, digest).hex()


def _make_solana_keypair():
    sk = nacl.signing.SigningKey.generate()
    addr = _encode_base58(bytes(sk.verify_key))
    return sk, addr


def _register_agent(client, name: str) -> dict:
    resp = client.post(
        "/api/register",
        json={"agent_name": name, "display_name": name.title(), "bio": "tester"},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _issue_and_verify(client, api_key: str, chain: str, address: str, signer_fn):
    chal_resp = client.post(
        "/api/agents/me/wallet/challenge",
        json={"chain": chain, "address": address},
        headers={"X-API-Key": api_key},
    )
    assert chal_resp.status_code == 200, chal_resp.get_json()
    chal = chal_resp.get_json()
    sig = signer_fn(chal["message"])
    ver_resp = client.post(
        "/api/agents/me/wallet/verify",
        json={"challenge_id": chal["challenge_id"], "signature": sig},
        headers={"X-API-Key": api_key},
    )
    assert ver_resp.status_code == 200, ver_resp.get_json()
    return chal, ver_resp.get_json()


def test_self_asserted_deposit_wallet_binding_blocked_without_pop(client):
    _victim_priv, victim_pub = _make_secp256k1_keypair()
    victim_eth = _eth_address_from_pub(victim_pub)
    _, victim_sol = _make_solana_keypair()
    _erg_priv, erg_pub = _make_secp256k1_keypair()
    victim_erg = _ergo_address_from_pub(erg_pub)

    mallory = _register_agent(client, "mallory_pop")
    headers = {"X-API-Key": mallory["api_key"]}

    for chain, addr in (("eth", victim_eth), ("sol", victim_sol), ("erg", victim_erg)):
        resp = client.post(
            "/api/agents/me/wallet",
            json={chain: addr, "btc": "bc1shouldnotwrite"},
            headers=headers,
        )
        assert resp.status_code == 403, (chain, resp.get_json())
        assert resp.get_json()["code"] == "WALLET_VERIFICATION_REQUIRED"

    # Partial write did not happen when rejected: btc & chain addresses remain empty.
    wallet = client.get("/api/agents/me/wallet", headers=headers).get_json()
    assert wallet["wallets"]["eth"] == ""
    assert wallet["wallets"]["sol"] == ""
    assert wallet["wallets"]["erg"] == ""
    assert wallet["wallets"]["btc"] == ""
    assert wallet["verified_wallets"] == {"eth": False, "sol": False, "erg": False}


def test_attack_blocked_then_legitimate_owner_verifies_and_deposits_usdc(client, monkeypatch):
    alice_priv, alice_pub = _make_secp256k1_keypair()
    alice_eth = _eth_address_from_pub(alice_pub)
    alice = _register_agent(client, "alice_usdc")
    mallory = _register_agent(client, "mallory_usdc")

    tx_hash = "0x" + "1a" * 32
    monkeypatch.setattr(
        usdc,
        "verify_usdc_transfer_onchain",
        lambda _tx: (
            {
                "tx_hash": _tx,
                "from_address": alice_eth.lower(),
                "to_address": usdc.TREASURY_ADDRESS.lower(),
                "amount_raw": "25000000",
                "amount_usdc": 25.0,
                "block_number": 9001,
                "chain": "base",
                "verified": True,
            },
            None,
        ),
    )

    # 1. Mallory fails to bind Alice's ETH address via self-assertion and cannot steal deposit.
    bind_attempt = client.post(
        "/api/agents/me/wallet",
        json={"eth": alice_eth},
        headers={"X-API-Key": mallory["api_key"]},
    )
    assert bind_attempt.status_code == 403
    steal_attempt = client.post(
        "/api/usdc/deposit",
        json={"tx_hash": tx_hash},
        headers={"X-API-Key": mallory["api_key"]},
    )
    assert steal_attempt.status_code == 400

    # 2. Even if an attacker already injected alice_eth directly in SQLite before patch,
    #    /api/usdc/deposit refuses unverified self-asserted ownership with 403 WALLET_NOT_VERIFIED.
    with client.application.app_context():
        db = sys.modules["bottube_server"].get_db()
        db.execute(
            "UPDATE agents SET eth_address = ? WHERE agent_name = ?",
            (alice_eth.lower(), "mallory_usdc"),
        )
        db.commit()

    legacy_bypass = client.post(
        "/api/usdc/deposit",
        json={"tx_hash": tx_hash},
        headers={"X-API-Key": mallory["api_key"]},
    )
    assert legacy_bypass.status_code == 403, legacy_bypass.get_json()
    assert legacy_bypass.get_json()["code"] == "WALLET_NOT_VERIFIED"

    # 3. Alice proves ownership via EIP-191 personal_sign and claims her USDC deposit cleanly.
    _, ver = _issue_and_verify(
        client, alice["api_key"], "eth", alice_eth.upper().replace("0X", "0x"), lambda m: _sign_eip191(alice_priv, m)
    )
    assert ver["verified"] is True
    assert ver["address"] == alice_eth.lower()

    alice_dep = client.post(
        "/api/usdc/deposit",
        json={"tx_hash": tx_hash},
        headers={"X-API-Key": alice["api_key"]},
    )
    assert alice_dep.status_code == 200, alice_dep.get_json()
    assert alice_dep.get_json()["balance_usdc"] == pytest.approx(25.0)

    # 4. Now that Alice verified alice_eth, Mallory cannot claim or verify the same ETH address.
    dup_chal = client.post(
        "/api/agents/me/wallet/challenge",
        json={"chain": "eth", "address": alice_eth},
        headers={"X-API-Key": mallory["api_key"]},
    )
    assert dup_chal.status_code == 409
    assert dup_chal.get_json()["code"] == "WALLET_ALREADY_CLAIMED"


def test_challenge_replay_expiry_malleability_and_cross_agent_hijack_rejected(client):
    alice_priv, alice_pub = _make_secp256k1_keypair()
    alice_eth = _eth_address_from_pub(alice_pub)
    other_priv, _ = _make_secp256k1_keypair()

    alice = _register_agent(client, "alice_sec")
    bob = _register_agent(client, "bob_sec")

    # Request challenge for Alice
    chal = client.post(
        "/api/agents/me/wallet/challenge",
        json={"chain": "eth", "address": alice_eth},
        headers={"X-API-Key": alice["api_key"]},
    ).get_json()
    valid_sig = _sign_eip191(alice_priv, chal["message"])

    # Bob cannot hijack Alice's challenge_id even with Alice's valid signature
    hijack = client.post(
        "/api/agents/me/wallet/verify",
        json={"challenge_id": chal["challenge_id"], "signature": valid_sig},
        headers={"X-API-Key": bob["api_key"]},
    )
    assert hijack.status_code == 403
    assert hijack.get_json()["code"] == "CHALLENGE_FORBIDDEN"

    # Wrong signer fails with 403
    wrong_sig = client.post(
        "/api/agents/me/wallet/verify",
        json={"challenge_id": chal["challenge_id"], "signature": _sign_eip191(other_priv, chal["message"])},
        headers={"X-API-Key": alice["api_key"]},
    )
    assert wrong_sig.status_code == 403
    assert wrong_sig.get_json()["code"] == "INVALID_WALLET_SIGNATURE"

    # High-s malleable signature fails EIP-2 check
    sig_raw = bytearray.fromhex(valid_sig[2:])
    s_low = int.from_bytes(sig_raw[32:64], "big")
    s_high = wv._SECP256K1_N - s_low
    sig_raw[32:64] = s_high.to_bytes(32, "big")
    sig_raw[64] = 28 if sig_raw[64] == 27 else 27
    high_s = client.post(
        "/api/agents/me/wallet/verify",
        json={"challenge_id": chal["challenge_id"], "signature": "0x" + sig_raw.hex()},
        headers={"X-API-Key": alice["api_key"]},
    )
    assert high_s.status_code == 403
    assert high_s.get_json()["code"] == "INVALID_WALLET_SIGNATURE"

    # Valid signature succeeds once, then replay returns 409
    first = client.post(
        "/api/agents/me/wallet/verify",
        json={"challenge_id": chal["challenge_id"], "signature": valid_sig},
        headers={"X-API-Key": alice["api_key"]},
    )
    assert first.status_code == 200
    replay = client.post(
        "/api/agents/me/wallet/verify",
        json={"challenge_id": chal["challenge_id"], "signature": valid_sig},
        headers={"X-API-Key": alice["api_key"]},
    )
    assert replay.status_code == 409
    assert replay.get_json()["code"] == "CHALLENGE_ALREADY_USED"

    # Expired challenge returns 400 CHALLENGE_EXPIRED
    exp_chal = client.post(
        "/api/agents/me/wallet/challenge",
        json={"chain": "eth", "address": alice_eth},
        headers={"X-API-Key": alice["api_key"]},
    ).get_json()
    with client.application.app_context():
        db = sys.modules["bottube_server"].get_db()
        db.execute(
            "UPDATE wallet_verification_challenges SET expires_at = ? WHERE challenge_id = ?",
            (time.time() - 10, exp_chal["challenge_id"]),
        )
        db.commit()
    expired = client.post(
        "/api/agents/me/wallet/verify",
        json={"challenge_id": exp_chal["challenge_id"], "signature": _sign_eip191(alice_priv, exp_chal["message"])},
        headers={"X-API-Key": alice["api_key"]},
    )
    assert expired.status_code == 400
    assert expired.get_json()["code"] == "CHALLENGE_EXPIRED"

    # Clearing verified eth wallet unbinds it and flips verified_wallets['eth'] back to False
    cleared = client.post(
        "/api/agents/me/wallet",
        json={"eth": ""},
        headers={"X-API-Key": alice["api_key"]},
    )
    assert cleared.status_code == 200
    assert client.get("/api/agents/me/wallet", headers={"X-API-Key": alice["api_key"]}).get_json()["verified_wallets"]["eth"] is False


def test_solana_and_ergo_pop_verification_and_all_bridge_defense_in_depth(client, monkeypatch, tmp_path):
    eth_priv, eth_pub = _make_secp256k1_keypair()
    eth_addr = _eth_address_from_pub(eth_pub)
    sol_sk, sol_addr = _make_solana_keypair()
    erg_priv, erg_pub = _make_secp256k1_keypair()
    erg_addr = _ergo_address_from_pub(erg_pub)

    attacker = _register_agent(client, "bridge_attacker")
    owner = _register_agent(client, "bridge_owner")

    # Seed unverified addresses directly into attacker's DB row to prove every bridge rejects unverified rows.
    with client.application.app_context():
        db = sys.modules["bottube_server"].get_db()
        db.execute(
            "UPDATE agents SET eth_address = ?, sol_address = ?, erg_address = ? WHERE agent_name = ?",
            (eth_addr, sol_addr, erg_addr, "bridge_attacker"),
        )
        db.commit()

    monkeypatch.setattr(base_bridge, "WRTC_BRIDGE_ENABLED", True)
    monkeypatch.setattr(base_bridge, "BASE_RESERVE_WALLET", "0x" + "9" * 40)
    monkeypatch.setattr(base_bridge, "verify_base_wrtc_transfer", lambda _tx: pytest.fail("base RPC should not run"))
    monkeypatch.setattr(sol_bridge, "WRTC_BRIDGE_ENABLED", True)
    monkeypatch.setattr(sol_bridge, "verify_wrtc_transfer", lambda _tx: pytest.fail("solana RPC should not run"))
    monkeypatch.setattr(ergo_bridge, "verify_ergo_tx", lambda _tx: pytest.fail("ergo RPC should not run"))

    att_hdr = {"X-API-Key": attacker["api_key"]}
    for endpoint, payload in (
        ("/api/base-bridge/deposit", {"tx_hash": "0x" + "a" * 64}),
        ("/api/wrtc-bridge/deposit", {"tx_signature": "5" * 44}),
        ("/api/ergo/deposit", {"tx_id": "b" * 64}),
    ):
        resp = client.post(endpoint, json=payload, headers=att_hdr)
        assert resp.status_code == 403, (endpoint, resp.get_json())
        assert resp.get_json()["code"] == "WALLET_NOT_VERIFIED"

    # Legacy wrtc_bridge.py HTTP route defense-in-depth check
    legacy_db_path = tmp_path / "legacy_bridge.db"
    conn = sqlite3.connect(str(legacy_db_path))
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            sol_address TEXT DEFAULT '',
            rtc_balance REAL DEFAULT 0
        );
        CREATE TABLE wrtc_deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_signature TEXT UNIQUE,
            from_address TEXT,
            amount_wrtc REAL,
            agent_id INTEGER,
            status TEXT DEFAULT 'credited',
            created_at REAL
        );
        CREATE TABLE earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            reason TEXT NOT NULL,
            video_id TEXT DEFAULT '',
            created_at REAL NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO agents (id, agent_name, api_key, sol_address, rtc_balance) VALUES (1, 'legacy_att', 'k_att', ?, 0.0)",
        (sol_addr,),
    )
    conn.execute(
        "INSERT INTO agents (id, agent_name, api_key, sol_address, rtc_balance) VALUES (2, 'legacy_own', 'k_own', ?, 0.0)",
        (sol_addr,),
    )
    wv.init_wallet_verification_tables(conn)
    conn.execute(
        "INSERT INTO verified_wallets (chain, address, agent_id, agent_name, verified_at, challenge_id) VALUES ('sol', ?, 2, 'legacy_own', 1000.0, 'c_own')",
        (sol_addr,),
    )
    conn.commit()
    conn.close()

    legacy_app = Flask("legacy_wrtc_test")
    legacy_app.config["TESTING"] = True

    def _legacy_get_db():
        if "legacy_db" not in g:
            g.legacy_db = sqlite3.connect(str(legacy_db_path))
            g.legacy_db.row_factory = sqlite3.Row
        return g.legacy_db

    @legacy_app.teardown_appcontext
    def _close_legacy_db(_exc):
        db = g.pop("legacy_db", None)
        if db is not None:
            db.close()

    monkeypatch.setattr(legacy_wrtc, "_get_db", _legacy_get_db)
    monkeypatch.setattr(
        legacy_wrtc,
        "verify_solana_deposit",
        lambda _tx: pytest.fail("legacy RPC should not run"),
    )
    legacy_app.register_blueprint(legacy_wrtc.wrtc_bridge_bp)
    legacy_client = legacy_app.test_client()

    leg_blocked = legacy_client.post(
        "/api/bridge/deposit",
        json={"tx_signature": "7" * 64},
        headers={"X-API-Key": "k_att"},
    )
    assert leg_blocked.status_code == 403, leg_blocked.get_json()
    assert leg_blocked.get_json()["code"] == "WALLET_NOT_VERIFIED"

    monkeypatch.setattr(
        legacy_wrtc,
        "verify_solana_deposit",
        lambda _tx: ({"from_address": sol_addr, "amount_wrtc": 4.0}, None),
    )
    leg_ok = legacy_client.post(
        "/api/bridge/deposit",
        json={"tx_signature": "7" * 64},
        headers={"X-API-Key": "k_own"},
    )
    assert leg_ok.status_code == 200, leg_ok.get_json()
    assert leg_ok.get_json()["ok"] is True

    # Now legitimate owner verifies ETH, SOL (Base58 sig), and ERG (Blake2b-256 ECDSA sig)
    _issue_and_verify(client, owner["api_key"], "eth", eth_addr, lambda m: _sign_eip191(eth_priv, m))
    _issue_and_verify(
        client,
        owner["api_key"],
        "sol",
        sol_addr,
        lambda m: _encode_base58(sol_sk.sign(m.encode("utf-8")).signature),
    )
    _issue_and_verify(client, owner["api_key"], "erg", erg_addr, lambda m: _sign_ergo(erg_priv, m))

    monkeypatch.setattr(
        base_bridge,
        "verify_base_wrtc_transfer",
        lambda _tx: (
            {
                "tx_hash": _tx,
                "from_address": eth_addr,
                "to_address": base_bridge.BASE_RESERVE_WALLET,
                "amount_raw": "5000000",
                "amount_wrtc": 5.0,
                "block_number": 100,
                "chain": "base",
            },
            None,
        ),
    )
    monkeypatch.setattr(
        sol_bridge,
        "verify_wrtc_transfer",
        lambda _tx: (
            {
                "tx_signature": _tx,
                "mint": sol_bridge.WRTC_MINT,
                "reserve_address": sol_bridge.WRTC_RESERVE_WALLET,
                "sender_address": sol_addr,
                "amount_raw": "3000000",
                "amount_wrtc": 3.0,
                "slot": 50,
                "block_time": 1000,
            },
            None,
        ),
    )
    monkeypatch.setattr(
        ergo_bridge,
        "verify_ergo_tx",
        lambda _tx: {
            "ok": True,
            "amount_erg": 2.0,
            "from_address": erg_addr,
            "confirmations": ergo_bridge.REQUIRED_CONFIRMATIONS,
            "tx_id": _tx,
        },
    )

    own_hdr = {"X-API-Key": owner["api_key"]}
    r_base = client.post("/api/base-bridge/deposit", json={"tx_hash": "0x" + "c" * 64}, headers=own_hdr)
    assert r_base.status_code == 200, r_base.get_json()
    r_sol = client.post("/api/wrtc-bridge/deposit", json={"tx_signature": "6" * 44}, headers=own_hdr)
    assert r_sol.status_code == 200, r_sol.get_json()
    r_erg = client.post("/api/ergo/deposit", json={"tx_id": "d" * 64}, headers=own_hdr)
    assert r_erg.status_code == 200, r_erg.get_json()
