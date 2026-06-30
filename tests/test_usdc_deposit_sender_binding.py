# SPDX-License-Identifier: MIT
"""Security regression tests for USDC deposit sender-binding (anti-theft).

A USDC->treasury tx_hash is PUBLIC on-chain data, and the deposit endpoint
dedups only per-tx_hash. Without binding the on-chain sender to the
authenticated account's wallet, any authenticated agent could claim someone
else's (or any unclaimed) treasury USDC transfer as their own balance credit
-- the same theft the wRTC Solana/Base bridges already block by requiring
sender == account wallet. These tests pin that binding into /api/usdc/deposit.
"""

import sqlite3
from importlib import metadata

import pytest
import werkzeug
from flask import Flask, g


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


ALICE_WALLET = "0x1111111111111111111111111111111111111111"
MALLORY_WALLET = "0x2222222222222222222222222222222222222222"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    import usdc_blueprint as usdc

    db_path = tmp_path / "usdc.db"
    conn = sqlite3.connect(str(db_path))
    # Mirror the production agents columns the USDC blueprint reads:
    # `name` (its auth helper) + `eth_address` (the new sender binding).
    conn.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            agent_name TEXT,
            api_key TEXT NOT NULL,
            eth_address TEXT,
            rtc_balance REAL DEFAULT 0
        )
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, agent_name, api_key, eth_address) VALUES (?, ?, ?, ?)",
        [
            ("alice", "alice", "k_alice", ALICE_WALLET),
            ("mallory", "mallory", "k_mallory", MALLORY_WALLET),
            ("carol", "carol", "k_carol", ""),  # no wallet bound
        ],
    )
    conn.commit()
    conn.close()

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(usdc.usdc_bp)

    def _test_get_db():
        if "test_db" in g:
            return g.test_db
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        g.test_db = db
        return db

    monkeypatch.setattr(usdc, "get_db", _test_get_db)

    # The on-chain transfer is "really" sent by ALICE_WALLET to the treasury.
    def _fake_verify(tx_hash):
        return (
            {
                "tx_hash": tx_hash,
                "from_address": ALICE_WALLET.lower(),
                "to_address": usdc.TREASURY_ADDRESS.lower(),
                "amount_raw": str(100 * 10 ** usdc.USDC_DECIMALS),
                "amount_usdc": 100.0,
                "block_number": 123,
                "chain": "base",
                "verified": True,
            },
            None,
        )

    monkeypatch.setattr(usdc, "verify_usdc_transfer_onchain", _fake_verify)

    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def _deposit(client, api_key, tx_hash):
    return client.post(
        "/api/usdc/deposit",
        json={"tx_hash": tx_hash},
        headers={"X-API-Key": api_key},
    )


def _balance(client, name):
    with client.application.app_context():
        import usdc_blueprint as usdc

        db = usdc.get_db()
        row = db.execute(
            "SELECT balance_usdc FROM usdc_balances WHERE agent_name = ?", (name,)
        ).fetchone()
        return row["balance_usdc"] if row else 0.0


def test_deposit_succeeds_when_sender_matches_bound_wallet(client):
    resp = _deposit(client, "k_alice", "0x" + "a" * 64)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["ok"] is True
    assert _balance(client, "alice") == 100.0


def test_deposit_blocks_claiming_another_users_transfer(client):
    # Mallory tries to claim Alice's treasury transfer. Must be rejected (403)
    # and must NOT credit Mallory.
    resp = _deposit(client, "k_mallory", "0x" + "b" * 64)
    assert resp.status_code == 403, resp.get_json()
    assert "does not match" in resp.get_json()["error"].lower()
    assert _balance(client, "mallory") == 0.0


def test_deposit_requires_bound_wallet(client):
    resp = _deposit(client, "k_carol", "0x" + "c" * 64)
    assert resp.status_code == 400, resp.get_json()
    assert "no ethereum wallet" in resp.get_json()["error"].lower()
    assert _balance(client, "carol") == 0.0


def test_rejected_deposit_is_not_recorded(client):
    _deposit(client, "k_mallory", "0x" + "d" * 64)
    with client.application.app_context():
        import usdc_blueprint as usdc

        db = usdc.get_db()
        usdc.init_usdc_tables(db)
        count = db.execute("SELECT COUNT(*) FROM usdc_deposits").fetchone()[0]
    assert count == 0


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
