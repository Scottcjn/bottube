# SPDX-License-Identifier: MIT
"""The /api/rtc/pay debit must be decided by the database, not by a stale read.

The balance compared against ``total_cost`` is read once, when the API key is
resolved. By the time the ``UPDATE`` runs it is only a memory of what the
balance used to be. Written as a bare ``rtc_balance = rtc_balance - ?`` the
statement always succeeds, so anything that changed the balance in between
(a concurrent purchase, a withdrawal) is simply overwritten and the account
goes negative.

Re-asserting ``rtc_balance >= ?`` inside the UPDATE turns the check into one
that can actually fail: rowcount 0 means the funds were not there, and the
whole purchase rolls back.
"""

import sqlite3

import pytest
from flask import Flask


@pytest.fixture()
def app(tmp_path):
    import rtc_services

    db_path = tmp_path / "rtc_services_guard.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            rtc_balance REAL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            reason TEXT DEFAULT '',
            video_id TEXT DEFAULT '',
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO agents (agent_name, api_key, rtc_balance) VALUES (?, ?, ?)",
        ("payer", "bottube_sk_payer", 60.0),
    )
    conn.commit()
    conn.close()

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    rtc_services.init_app(flask_app, db_path)
    flask_app.config["RTC_TEST_DB"] = str(db_path)
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def _balance(app, api_key="bottube_sk_payer"):
    conn = sqlite3.connect(app.config["RTC_TEST_DB"])
    try:
        return conn.execute(
            "SELECT rtc_balance FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()[0]
    finally:
        conn.close()


def _set_balance(app, value, api_key="bottube_sk_payer"):
    conn = sqlite3.connect(app.config["RTC_TEST_DB"])
    try:
        conn.execute(
            "UPDATE agents SET rtc_balance = ? WHERE api_key = ?", (value, api_key)
        )
        conn.commit()
    finally:
        conn.close()


def test_stale_balance_read_cannot_overdraw(client, app, monkeypatch):
    """A balance that was true at auth time but is not true now must not pay.

    Simulates the interleaving of two concurrent purchases: the request holds
    an agent row that still says 60 RTC while the row on disk is down to 1.
    """
    import rtc_services

    real_get_agent = rtc_services._get_agent

    def stale_agent(db):
        agent = dict(real_get_agent(db))
        agent["rtc_balance"] = 60.0  # what the balance was, not what it is
        return agent

    monkeypatch.setattr(rtc_services, "_get_agent", stale_agent)
    _set_balance(app, 1.0)

    resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "pro_api_month", "quantity": 1},
        headers={"X-API-Key": "bottube_sk_payer"},
    )

    assert resp.status_code != 200, resp.get_json()
    assert _balance(app) == 1.0, "balance must not go negative on a stale read"


def test_stale_balance_read_leaves_no_purchase_record(client, app, monkeypatch):
    """A refused debit must not leave a paid-looking purchase behind."""
    import rtc_services

    real_get_agent = rtc_services._get_agent

    def stale_agent(db):
        agent = dict(real_get_agent(db))
        agent["rtc_balance"] = 60.0
        return agent

    monkeypatch.setattr(rtc_services, "_get_agent", stale_agent)
    _set_balance(app, 1.0)

    client.post(
        "/api/rtc/pay",
        json={"service_key": "pro_api_month", "quantity": 1},
        headers={"X-API-Key": "bottube_sk_payer"},
    )

    conn = sqlite3.connect(app.config["RTC_TEST_DB"])
    try:
        purchases = conn.execute("SELECT COUNT(*) FROM service_purchases").fetchone()[0]
        earnings = conn.execute("SELECT COUNT(*) FROM earnings").fetchone()[0]
    finally:
        conn.close()

    assert purchases == 0
    assert earnings == 0


def test_funded_purchase_still_succeeds(client, app):
    """Control: the guard must not break the ordinary paid path."""
    resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "pro_api_month", "quantity": 1},
        headers={"X-API-Key": "bottube_sk_payer"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert _balance(app) == 0.0
