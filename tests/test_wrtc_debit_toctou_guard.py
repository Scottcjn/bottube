# SPDX-License-Identifier: MIT
"""Regression tests for wRTC bridge RTC debit atomicity (Fixes #1620).

``wrtc_bridge._debit_rtc`` used a check-then-update sequence: two concurrent
withdrawals could both observe the same balance, both pass the gate, and both
subtract -- overdrawing the account. The fix pushes the comparison into the
UPDATE (``AND rtc_balance >= ?``) and treats ``rowcount == 0`` as insufficient
funds.
"""

import sqlite3
import tempfile
import os

import pytest

import wrtc_bridge


def test_debit_rtc_rejects_insufficient_balance():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, rtc_balance REAL)")
        db.execute("INSERT INTO agents (id, rtc_balance) VALUES (1, 9.9)")
        db.commit()

        assert wrtc_bridge._debit_rtc(db, 1, 10.0) is False
        db.commit()
        assert db.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()[0] == 9.9
    finally:
        os.unlink(path)


def test_debit_rtc_atomic_against_stale_read():
    """Two connections both read 60.0; only one guarded UPDATE may win."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        setup = sqlite3.connect(path)
        setup.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, rtc_balance REAL)")
        setup.execute("INSERT INTO agents (id, rtc_balance) VALUES (1, 60.0)")
        setup.commit()
        setup.close()

        a = sqlite3.connect(path, timeout=5)
        b = sqlite3.connect(path, timeout=5)
        a.row_factory = sqlite3.Row
        b.row_factory = sqlite3.Row
        try:
            assert a.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()[0] == 60.0
            assert b.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()[0] == 60.0

            first = wrtc_bridge._debit_rtc(a, 1, 60.0)
            a.commit()
            second = wrtc_bridge._debit_rtc(b, 1, 60.0)
            b.commit()

            assert first is True
            assert second is False
            final = b.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()[0]
            assert final == pytest.approx(0.0)
        finally:
            a.close()
            b.close()
    finally:
        os.unlink(path)
