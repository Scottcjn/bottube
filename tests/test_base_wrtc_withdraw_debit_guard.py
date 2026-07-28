# SPDX-License-Identifier: MIT
"""The Base wRTC withdrawal debit must be decided by the database.

``/api/base-bridge/withdraw`` read the balance off the agent row loaded at
authentication time, compared it to the requested amount, INSERTed the pending
withdrawal, and only then ran a bare ``rtc_balance = rtc_balance - ?``. That
UPDATE cannot fail, so the balance check was advisory: two requests that both
passed it each queued a payout against the same funds and the account went
negative. The payout rows survived because they were written before the debit.

Re-asserting ``rtc_balance >= ?`` in the UPDATE gives the check something to
report, and rolling back on rowcount 0 also discards the queued withdrawal.
"""

import sqlite3

import pytest
import werkzeug
from flask import Flask, g

from importlib import metadata


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


AGENT_ADDRESS = "0x1111111111111111111111111111111111111111"
DEST_ADDRESS = "0x2222222222222222222222222222222222222222"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    import base_wrtc_bridge_blueprint as bridge

    db_path = tmp_path / "base_bridge_guard.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            eth_address TEXT,
            rtc_balance REAL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO agents (agent_name, api_key, eth_address, rtc_balance)
        VALUES (?, ?, ?, ?)
        """,
        ("bridgeuser", "bottube_sk_bridgeuser", AGENT_ADDRESS, 100.0),
    )
    conn.commit()
    conn.close()

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["BRIDGE_TEST_DB"] = str(db_path)
    flask_app.register_blueprint(bridge.base_wrtc_bp)

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


def _query(app, sql, args=()):
    conn = sqlite3.connect(app.config["BRIDGE_TEST_DB"])
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def _balance(app):
    return _query(app, "SELECT rtc_balance FROM agents WHERE id = 1")[0]


def _set_balance(app, value):
    conn = sqlite3.connect(app.config["BRIDGE_TEST_DB"])
    try:
        conn.execute("UPDATE agents SET rtc_balance = ? WHERE id = 1", (value,))
        conn.commit()
    finally:
        conn.close()


def _stale_agent(monkeypatch, claimed_balance):
    """Pin the auth-time agent row to a balance that is no longer true."""
    import base_wrtc_bridge_blueprint as bridge

    monkeypatch.setattr(
        bridge,
        "_get_authenticated_agent",
        lambda: {
            "id": 1,
            "agent_name": "bridgeuser",
            "eth_address": AGENT_ADDRESS,
            "rtc_balance": claimed_balance,
        },
    )


def test_stale_balance_cannot_overdraw(client, app, monkeypatch):
    _stale_agent(monkeypatch, 100.0)
    _set_balance(app, 5.0)

    resp = client.post(
        "/api/base-bridge/withdraw",
        json={"to_address": DEST_ADDRESS, "amount": 50.0},
        headers={"X-API-Key": "bottube_sk_bridgeuser"},
    )

    assert resp.status_code == 409, resp.get_json()
    assert _balance(app) == 5.0


def test_refused_withdrawal_is_not_left_queued(client, app, monkeypatch):
    """The withdrawal row is INSERTed before the debit, so it must roll back."""
    _stale_agent(monkeypatch, 100.0)
    _set_balance(app, 5.0)

    client.post(
        "/api/base-bridge/withdraw",
        json={"to_address": DEST_ADDRESS, "amount": 50.0},
        headers={"X-API-Key": "bottube_sk_bridgeuser"},
    )

    queued = _query(app, "SELECT COUNT(*) FROM base_wrtc_withdrawals")[0]
    assert queued == 0, "a payout must not stay queued against money that is gone"


def test_funded_withdrawal_still_succeeds(client, app):
    """Control: the guard must not break an ordinary withdrawal."""
    resp = client.post(
        "/api/base-bridge/withdraw",
        json={"to_address": DEST_ADDRESS, "amount": 50.0},
        headers={"X-API-Key": "bottube_sk_bridgeuser"},
    )

    assert resp.status_code == 200, resp.get_json()
    assert _balance(app) == pytest.approx(49.5)
    assert _query(app, "SELECT COUNT(*) FROM base_wrtc_withdrawals")[0] == 1
