# SPDX-License-Identifier: MIT
"""Validation tests for Ergo bridge request parsing."""

import sqlite3

import pytest
from flask import Flask, g

import ergo_bridge_blueprint


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "ergo_bridge.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            rtc_balance REAL DEFAULT 0
        );
        CREATE TABLE earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            amount REAL,
            source TEXT,
            created_at REAL
        );
        INSERT INTO agents (agent_name, api_key, rtc_balance)
        VALUES ('ergo_agent', 'bottube_sk_ergo_agent', 100.0);
        """
    )
    ergo_bridge_blueprint.init_ergo_tables(conn)
    conn.commit()
    conn.close()

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.register_blueprint(ergo_bridge_blueprint.ergo_bp)

    def _test_get_db():
        if "test_db" in g:
            return g.test_db
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        g.test_db = db
        return db

    @app.teardown_appcontext
    def _close_db(_exc):
        db = g.pop("test_db", None)
        if db is not None:
            db.close()

    monkeypatch.setattr(ergo_bridge_blueprint, "get_db", _test_get_db)

    test_client = app.test_client()
    test_client.db_path = db_path
    return test_client


def _auth_headers():
    return {"X-API-Key": "bottube_sk_ergo_agent"}


def _counts_and_balance(db_path):
    with sqlite3.connect(str(db_path)) as db:
        return {
            "deposits": db.execute("SELECT COUNT(*) FROM ergo_deposits").fetchone()[0],
            "withdrawals": db.execute(
                "SELECT COUNT(*) FROM ergo_withdrawals"
            ).fetchone()[0],
            "balance": db.execute(
                "SELECT rtc_balance FROM agents WHERE api_key = ?",
                ("bottube_sk_ergo_agent",),
            ).fetchone()[0],
        }


def test_ergo_deposit_rejects_non_object_json(client):
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/deposit",
        json=["not", "an", "object"],
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"
    assert _counts_and_balance(client.db_path) == before


def test_ergo_deposit_rejects_non_string_tx_id(client):
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/deposit",
        json={"tx_id": ["abc"]},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "tx_id must be a string"
    assert _counts_and_balance(client.db_path) == before


def test_ergo_withdraw_rejects_non_object_json(client):
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/withdraw",
        json=[{"amount_rtc": 10, "address": "9abc"}],
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"
    assert _counts_and_balance(client.db_path) == before


def test_ergo_withdraw_rejects_non_string_address(client):
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/withdraw",
        json={"amount_rtc": 10, "address": ["9abc"]},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "address must be a string"
    assert _counts_and_balance(client.db_path) == before


@pytest.mark.parametrize("amount", ["abc", "NaN", "Infinity", True, 0, -1])
def test_ergo_withdraw_rejects_invalid_amount_without_queue_or_debit(client, amount):
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/withdraw",
        json={"amount_rtc": amount, "address": "9abc"},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "amount_rtc must be a finite positive number"
    assert _counts_and_balance(client.db_path) == before


@pytest.mark.parametrize("limit", ["abc", "-5", "0"])
def test_ergo_history_rejects_invalid_limit(client, limit):
    app = client.application

    with app.test_request_context(
        f"/api/ergo/history?limit={limit}",
        headers=_auth_headers(),
    ):
        resp, status = ergo_bridge_blueprint.ergo_history()

    assert status == 400
    assert resp.get_json()["error"] == "limit must be a positive integer"


def test_ergo_history_clamps_large_limit(client):
    app = client.application

    with app.test_request_context(
        "/api/ergo/history?limit=500",
        headers=_auth_headers(),
    ):
        resp = ergo_bridge_blueprint.ergo_history()

    assert resp.status_code == 200
    assert resp.get_json() == {"deposits": [], "withdrawals": []}
