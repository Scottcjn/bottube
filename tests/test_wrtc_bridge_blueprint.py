import pathlib
import sqlite3
import sys

from flask import Flask, g

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wrtc_bridge_blueprint as wrtc  # noqa: E402


def _build_app(db_conn):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["DB_CONN"] = db_conn

    @app.before_request
    def _inject_db():
        g.db = app.config["DB_CONN"]

    app.register_blueprint(wrtc.wrtc_bp)
    return app


def _build_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            sol_address TEXT DEFAULT '',
            rtc_balance REAL DEFAULT 0
        )
        """
    )
    wrtc.init_wrtc_tables(db)
    db.execute(
        "INSERT INTO agents (id, agent_name, api_key, sol_address, rtc_balance) VALUES (1, 'alice', 'bottube_sk_test', 'SenderWallet1111111111111111111111111111111', 0)"
    )
    db.commit()
    return db


def test_deposit_requires_api_key():
    db = _build_db()
    app = _build_app(db)
    client = app.test_client()
    resp = client.post("/api/wrtc-bridge/deposit", json={"tx_signature": "abc123"})
    assert resp.status_code == 401
    assert "X-API-Key" in resp.get_json()["error"]


def test_verify_transfer_rejects_non_canonical_mint(monkeypatch):
    def fake_rpc(_method, _params):
        return {
            "result": {
                "slot": 123,
                "blockTime": 1700000000,
                "meta": {
                    "err": None,
                    "preTokenBalances": [],
                    "postTokenBalances": [
                        {
                            "accountIndex": 7,
                            "mint": "NotCanonicalMint111111111111111111111111111",
                            "owner": wrtc.WRTC_RESERVE_WALLET,
                            "uiTokenAmount": {"amount": "1000000"},
                        }
                    ],
                },
            }
        }

    monkeypatch.setattr(wrtc, "_rpc_call", fake_rpc)
    transfer, err = wrtc.verify_wrtc_transfer("5XdummySig")
    assert transfer is None
    assert err is not None
    assert "canonical" in err.lower()


def test_deposit_idempotency_prevents_double_credit(monkeypatch):
    db = _build_db()
    app = _build_app(db)
    client = app.test_client()

    def fake_verify(_tx_signature):
        return (
            {
                "tx_signature": "sig_unique_001_really_long_value_1234567890",
                "mint": wrtc.WRTC_MINT,
                "reserve_address": wrtc.WRTC_RESERVE_WALLET,
                "sender_address": "SenderWallet1111111111111111111111111111111",
                "amount_raw": "2500000",
                "amount_wrtc": 2.5,
                "slot": 42,
                "block_time": 1700000001,
            },
            None,
        )

    monkeypatch.setattr(wrtc, "verify_wrtc_transfer", fake_verify)
    headers = {"X-API-Key": "bottube_sk_test"}
    tx_sig = "sig_unique_001_really_long_value_1234567890"

    first = client.post("/api/wrtc-bridge/deposit", headers=headers, json={"tx_signature": tx_sig})
    assert first.status_code == 200
    assert first.get_json()["ok"] is True

    second = client.post("/api/wrtc-bridge/deposit", headers=headers, json={"tx_signature": tx_sig})
    assert second.status_code == 200
    assert second.get_json()["idempotent"] is True

    bal = db.execute("SELECT rtc_balance FROM agents WHERE id = 1").fetchone()["rtc_balance"]
    assert bal == 2.5
