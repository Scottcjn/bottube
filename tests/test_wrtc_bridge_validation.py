# SPDX-License-Identifier: MIT
"""Validation tests for Solana wRTC bridge request parsing."""

import sqlite3

import pytest
from flask import Flask, g


@pytest.fixture()
def app(tmp_path, monkeypatch):
    import wrtc_bridge_blueprint as bridge

    db_path = tmp_path / "wrtc_bridge.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            sol_address TEXT,
            rtc_balance REAL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO agents (agent_name, api_key, sol_address, rtc_balance)
        VALUES (?, ?, ?, ?)
        """,
        (
            "bridgeuser",
            "bottube_sk_bridgeuser",
            "11111111111111111111111111111111",
            1000.0,
        ),
    )
    conn.commit()
    conn.close()

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["DATABASE"] = str(db_path)
    flask_app.register_blueprint(bridge.wrtc_bp)

    def _test_get_db():
        if "test_db" in g:
            return g.test_db
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        g.test_db = db
        return db

    monkeypatch.setattr(bridge, "get_db", _test_get_db)

    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def _auth_headers():
    return {"X-API-Key": "bottube_sk_bridgeuser"}


def _withdraw(client, payload):
    return client.post(
        "/api/wrtc-bridge/withdraw",
        json=payload,
        headers=_auth_headers(),
    )


def test_wrtc_deposit_rejects_non_object_json(client):
    resp = client.post(
        "/api/wrtc-bridge/deposit",
        json=["not", "an", "object"],
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"


def test_wrtc_deposit_rejects_non_string_tx_signature(client, monkeypatch):
    import wrtc_bridge_blueprint as bridge

    monkeypatch.setattr(
        bridge,
        "verify_wrtc_transfer",
        lambda _tx_signature: pytest.fail("verification should not run"),
    )

    resp = client.post(
        "/api/wrtc-bridge/deposit",
        json={"tx_signature": ["abc"]},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "tx_signature must be a string"


def test_wrtc_withdraw_rejects_non_object_json(client):
    resp = _withdraw(client, [{"to_address": "11111111111111111111111111111111"}])

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"


def test_wrtc_withdraw_rejects_non_string_to_address(client):
    resp = _withdraw(
        client,
        {"to_address": ["11111111111111111111111111111111"], "amount": 10},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "to_address must be a string"


@pytest.mark.parametrize("amount", ["abc", "NaN", "Infinity", True])
def test_wrtc_withdraw_rejects_non_finite_amounts(client, amount):
    resp = _withdraw(
        client,
        {"to_address": "11111111111111111111111111111111", "amount": amount},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "amount must be a finite number"


def test_rejected_wrtc_withdrawal_does_not_queue_or_debit(client):
    resp = _withdraw(
        client,
        {"to_address": "11111111111111111111111111111111", "amount": "NaN"},
    )
    assert resp.status_code == 400

    import wrtc_bridge_blueprint as bridge

    with sqlite3.connect(client.application.config["DATABASE"]) as db:
        bridge.init_wrtc_tables(db)
        queued = db.execute("SELECT COUNT(*) FROM wrtc_withdrawals").fetchone()[0]
        balance = db.execute(
            "SELECT rtc_balance FROM agents WHERE api_key = ?",
            ("bottube_sk_bridgeuser",),
        ).fetchone()[0]

    assert queued == 0
    assert balance == 1000.0


@pytest.mark.parametrize(
    "path",
    [
        "/wrtc",
        "/wrtc/deposit",
        "/wrtc/withdraw",
        "/wrtc/history",
        "/premium/wrtc",
    ],
)
def test_wrtc_html_alias_routes_redirect_to_bridge_console(client, path):
    resp = client.get(path)

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/bridge/wrtc")
