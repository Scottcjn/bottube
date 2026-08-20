# SPDX-License-Identifier: MIT
"""Regression tests for the Ergo deposit credit path.

Two bugs are covered here:

1. ``_award_rtc`` inserted into ``earnings (agent_id, amount, source,
   created_at)``. The production schema (``bottube_server.py``) declares
   ``earnings(id, agent_id, amount, reason, video_id, created_at)`` and every
   other writer uses ``reason``. The bad column name raised
   ``sqlite3.OperationalError: table earnings has no column named source`` on
   every deposit, so the RTC credit never landed.

2. The ``ergo_deposits`` row was committed *before* the credit was attempted,
   so the failure above left the tx_id permanently claimed: retrying returned
   HTTP 409 "Transaction already claimed" while the agent had 0 RTC.

These tests build the fixture with the REAL ``earnings`` schema on purpose —
the older fixture invented a ``source`` column, which is exactly why the bug
survived the suite.
"""

import sqlite3

import pytest
import werkzeug
from flask import Flask, g

import ergo_bridge_blueprint


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "test"


API_KEY = "bottube_sk_ergo_credit"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "ergo_credit.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            rtc_balance REAL DEFAULT 0
        );
        -- Production schema, verbatim from bottube_server.py.
        CREATE TABLE earnings (
            id INTEGER PRIMARY KEY,
            agent_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            reason TEXT NOT NULL,
            video_id TEXT DEFAULT '',
            created_at REAL NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO agents (agent_name, api_key, rtc_balance) VALUES (?, ?, ?)",
        ("ergo_agent", API_KEY, 0.0),
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
    monkeypatch.setattr(
        ergo_bridge_blueprint,
        "verify_ergo_tx",
        lambda tx_id: {
            "ok": True,
            "amount_erg": 1.0,
            "confirmations": 3,
            "from_address": "9fSenderAddress",
        },
    )

    test_client = app.test_client()
    test_client.db_path = db_path
    return test_client


def _state(db_path):
    with sqlite3.connect(str(db_path)) as db:
        return {
            "balance": db.execute(
                "SELECT rtc_balance FROM agents WHERE api_key = ?", (API_KEY,)
            ).fetchone()[0],
            "deposits": db.execute(
                "SELECT COUNT(*) FROM ergo_deposits"
            ).fetchone()[0],
            "earnings": db.execute("SELECT COUNT(*) FROM earnings").fetchone()[0],
        }


def test_deposit_credits_rtc_and_writes_earnings_row(client):
    resp = client.post(
        "/api/ergo/deposit",
        json={"tx_id": "a" * 64},
        headers={"X-API-Key": API_KEY},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True

    # 1.0 ERG - 1% fee = 0.99 ERG net, x8.0 = 7.92 RTC
    expected_rtc = 7.92
    assert body["rtc_credited"] == pytest.approx(expected_rtc)

    state = _state(client.db_path)
    assert state["balance"] == pytest.approx(expected_rtc)
    assert state["deposits"] == 1
    assert state["earnings"] == 1

    with sqlite3.connect(str(client.db_path)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM earnings").fetchone()
    assert row["amount"] == pytest.approx(expected_rtc)
    assert row["reason"].startswith("ergo_deposit:")


def test_failed_credit_does_not_burn_the_tx_id(client, monkeypatch):
    """If the credit blows up, the deposit row must not survive.

    Otherwise the tx_id is claimed forever (409) with no RTC issued.
    """

    def _boom(db, agent_id, amount, reason):
        raise sqlite3.OperationalError("simulated credit failure")

    monkeypatch.setattr(ergo_bridge_blueprint, "_award_rtc", _boom)

    with pytest.raises(sqlite3.OperationalError):
        client.post(
            "/api/ergo/deposit",
            json={"tx_id": "b" * 64},
            headers={"X-API-Key": API_KEY},
        )

    state = _state(client.db_path)
    assert state["deposits"] == 0, "deposit row committed without a credit"
    assert state["balance"] == pytest.approx(0.0)
