# SPDX-License-Identifier: MIT
"""Regression tests: an RTC debit must never drive a balance negative.

``/api/rtc/pay`` used to read the caller's balance, compare it against the
cost, and *then* run an unguarded ``UPDATE agents SET rtc_balance =
rtc_balance - ?``.  The comment above it said "Atomic debit + purchase record",
but nothing about it was atomic: the read and the write were separate
statements against separate connections, so two concurrent purchases could both
observe the same balance, both pass the check, and both subtract -- minting
RTC out of an overdrawn account.

The fix pushes the comparison into the UPDATE (``AND rtc_balance >= ?``) and
treats ``rowcount == 0`` as "someone else spent it first".

These tests assert the *invariant* (balance never negative, RTC conserved)
rather than any particular interleaving, so they hold no matter how the
scheduler orders the threads.
"""

import sqlite3
import threading

import pytest
from flask import Flask


MONTH_PASS_COST = 60.0  # SERVICE_CATALOG["pro_api_month"]["price_rtc"]


@pytest.fixture()
def app(tmp_path):
    import rtc_services

    db_path = tmp_path / "rtc_debit_guard.db"
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


def _set_balance(app, amount):
    conn = sqlite3.connect(app.config["RTC_TEST_DB"])
    try:
        conn.execute(
            "UPDATE agents SET rtc_balance = ? WHERE api_key = ?",
            (amount, "bottube_sk_payer"),
        )
        conn.commit()
    finally:
        conn.close()


def _balance(app):
    conn = sqlite3.connect(app.config["RTC_TEST_DB"])
    try:
        return conn.execute(
            "SELECT rtc_balance FROM agents WHERE api_key = ?",
            ("bottube_sk_payer",),
        ).fetchone()[0]
    finally:
        conn.close()


def test_insufficient_balance_does_not_debit(client, app):
    """A purchase the caller cannot afford must leave the balance untouched."""
    _set_balance(app, MONTH_PASS_COST - 0.1)

    resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "pro_api_month", "quantity": 1},
        headers={"X-API-Key": "bottube_sk_payer"},
    )

    assert resp.status_code == 402, resp.get_json()
    assert _balance(app) == pytest.approx(MONTH_PASS_COST - 0.1)


def test_exact_balance_purchase_succeeds_and_lands_on_zero(client, app):
    """`rtc_balance >= cost` must be inclusive -- spending your last RTC works."""
    _set_balance(app, MONTH_PASS_COST)

    resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "pro_api_month", "quantity": 1},
        headers={"X-API-Key": "bottube_sk_payer"},
    )

    assert resp.status_code == 200, resp.get_json()
    assert _balance(app) == pytest.approx(0.0)


def test_concurrent_purchases_cannot_overdraw(client, app):
    """Concurrent purchases funded for exactly ONE must not overdraw.

    Before the guard, several threads could each read 60.0, each pass the
    balance check, and each subtract 60.0 -- ending at -180.0 with four service
    tokens issued for one payment.
    """
    _set_balance(app, MONTH_PASS_COST)

    threads_n = 8
    barrier = threading.Barrier(threads_n)
    statuses = []
    lock = threading.Lock()

    def buy():
        barrier.wait()
        resp = client.post(
            "/api/rtc/pay",
            json={"service_key": "pro_api_month", "quantity": 1},
            headers={"X-API-Key": "bottube_sk_payer"},
        )
        with lock:
            statuses.append(resp.status_code)

    threads = [threading.Thread(target=buy) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(statuses) == threads_n, "a worker thread did not finish"

    successes = statuses.count(200)
    final = _balance(app)

    # The core invariant: money is never created.
    assert final >= 0.0, f"balance went negative: {final} (statuses={statuses})"
    # At most one purchase can be funded by a single pass's worth of RTC.
    assert successes <= 1, f"{successes} purchases funded by one balance"
    # And RTC is conserved: every success is paid for out of the balance.
    assert final == pytest.approx(MONTH_PASS_COST - successes * MONTH_PASS_COST)


def test_guarded_update_is_atomic_against_a_stale_read():
    """Direct proof of the pattern: a stale pre-read cannot force an overdraw.

    Two connections both read a balance of 60.0 (the classic TOCTOU window),
    then both attempt the debit. With the guard in the WHERE clause exactly one
    UPDATE matches a row; the loser sees ``rowcount == 0``.
    """
    import tempfile
    import os

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        setup = sqlite3.connect(path)
        setup.execute(
            "CREATE TABLE agents (id INTEGER PRIMARY KEY, rtc_balance REAL)"
        )
        setup.execute("INSERT INTO agents (id, rtc_balance) VALUES (1, 60.0)")
        setup.commit()
        setup.close()

        a = sqlite3.connect(path, timeout=5)
        b = sqlite3.connect(path, timeout=5)
        try:
            # Both readers observe the same balance -- both would pass a
            # check-then-update style gate.
            assert a.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()[0] == 60.0
            assert b.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()[0] == 60.0

            cur_a = a.execute(
                "UPDATE agents SET rtc_balance = rtc_balance - ? "
                "WHERE id = ? AND rtc_balance >= ?",
                (60.0, 1, 60.0),
            )
            a.commit()

            cur_b = b.execute(
                "UPDATE agents SET rtc_balance = rtc_balance - ? "
                "WHERE id = ? AND rtc_balance >= ?",
                (60.0, 1, 60.0),
            )
            b.commit()

            assert cur_a.rowcount == 1, "first debit should win"
            assert cur_b.rowcount == 0, "second debit must find no funded row"

            final = b.execute(
                "SELECT rtc_balance FROM agents WHERE id=1"
            ).fetchone()[0]
            assert final == pytest.approx(0.0)
        finally:
            a.close()
            b.close()
    finally:
        os.unlink(path)
