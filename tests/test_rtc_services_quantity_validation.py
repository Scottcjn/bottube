# SPDX-License-Identifier: MIT
"""Validation tests for /api/rtc/pay quantity parsing.

``quantity`` arrives straight from the client body.  Without a sign/range
check the cost multiplies out negative, the balance gate compares against a
negative number (and so always passes), and the debit -- written as
``rtc_balance = rtc_balance - ?`` -- *adds* the amount instead.  Any
self-registered agent could mint RTC from a zero balance.
"""

import sqlite3

import pytest
from flask import Flask


@pytest.fixture()
def app(tmp_path):
    import rtc_services

    db_path = tmp_path / "rtc_services.db"
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
        ("payer", "bottube_sk_payer", 0.0),
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


@pytest.mark.parametrize("quantity", [-1, -1000])
def test_rtc_pay_rejects_negative_quantity(client, app, quantity):
    """A negative quantity must not invert the debit into a credit."""
    resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "pro_api_month", "quantity": quantity},
        headers={"X-API-Key": "bottube_sk_payer"},
    )
    assert resp.status_code == 400, resp.get_json()
    assert _balance(app) == 0.0


def test_rtc_pay_rejects_zero_quantity(client, app):
    """Zero quantity buys nothing and must not issue a free service token."""
    resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "pro_api_month", "quantity": 0},
        headers={"X-API-Key": "bottube_sk_payer"},
    )
    assert resp.status_code == 400, resp.get_json()
    assert _balance(app) == 0.0


def test_rtc_pay_rejects_non_integer_quantity(client, app):
    """A non-integer quantity is a client error, not an unhandled 500."""
    resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "pro_api_month", "quantity": "abc"},
        headers={"X-API-Key": "bottube_sk_payer"},
    )
    assert resp.status_code == 400, resp.get_json()
    assert _balance(app) == 0.0


def test_rtc_pay_still_debits_a_funded_purchase(client, app):
    """Control: the normal paid path is unchanged by the validation."""
    conn = sqlite3.connect(app.config["RTC_TEST_DB"])
    conn.execute("UPDATE agents SET rtc_balance = 60.0 WHERE api_key = ?",
                 ("bottube_sk_payer",))
    conn.commit()
    conn.close()

    resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "pro_api_month", "quantity": 1},
        headers={"X-API-Key": "bottube_sk_payer"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["service_token"]
    assert _balance(app) == 0.0
