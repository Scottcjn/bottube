"""Regression coverage for concurrent BAN ledger debit admission."""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from flask import Flask

import banano_blueprint


class _BarrierConnection:
    """Force unlocked balance reads to overlap, exposing the check/write race."""

    def __init__(self, path, barrier):
        self._conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._barrier = barrier
        self._write_locked = False

    def execute(self, sql, parameters=()):
        if sql.strip().upper() == "BEGIN IMMEDIATE":
            cursor = self._conn.execute(sql, parameters)
            self._write_locked = True
            return cursor
        cursor = self._conn.execute(sql, parameters)
        if " AS BALANCE " in f" {sql.upper()} " and not self._write_locked:
            self._barrier.wait(timeout=10)
        return cursor

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()


def test_concurrent_withdrawals_cannot_reserve_more_than_balance(tmp_path, monkeypatch):
    db_path = tmp_path / "bottube.db"
    setup = sqlite3.connect(db_path)
    banano_blueprint.init_ban_tables(setup)
    setup.execute(
        "INSERT INTO ban_transactions "
        "(agent_id,tx_type,amount_ban,reason,status,created_at) "
        "VALUES(1,'reward',10,'earned','credited',1)"
    )
    setup.commit()
    setup.close()

    barrier = threading.Barrier(2)
    connections = []

    def connection():
        db = _BarrierConnection(db_path, barrier)
        connections.append(db)
        return db

    monkeypatch.setattr(banano_blueprint, "get_db", connection)
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    app.register_blueprint(banano_blueprint.ban_bp)

    def withdraw(suffix):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = 1
            address = "ban_" + suffix * 60
            return client.post(
                "/ban/withdraw", json={"address": address, "amount": 8}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(withdraw, ("a", "b")))

    for db in connections:
        db.close()
    verify = sqlite3.connect(db_path)
    reserved = verify.execute(
        "SELECT COALESCE(SUM(amount_ban),0) FROM ban_transactions "
        "WHERE agent_id=1 AND tx_type='withdrawal' AND status='pending'"
    ).fetchone()[0]
    verify.close()

    assert sorted(statuses) == [200, 400]
    assert reserved == 8.0


def test_concurrent_tips_cannot_spend_more_than_balance(tmp_path, monkeypatch):
    db_path = tmp_path / "bottube.db"
    setup = sqlite3.connect(db_path)
    setup.execute(
        "CREATE TABLE agents (id INTEGER PRIMARY KEY, agent_name TEXT UNIQUE NOT NULL)"
    )
    setup.executemany(
        "INSERT INTO agents (id, agent_name) VALUES (?, ?)",
        [(1, "alice"), (2, "bob")],
    )
    banano_blueprint.init_ban_tables(setup)
    setup.execute(
        "INSERT INTO ban_transactions "
        "(agent_id,tx_type,amount_ban,reason,status,created_at) "
        "VALUES(1,'reward',10,'earned','credited',1)"
    )
    setup.commit()
    setup.close()

    barrier = threading.Barrier(2)
    connections = []

    def connection():
        db = _BarrierConnection(db_path, barrier)
        connections.append(db)
        return db

    monkeypatch.setattr(banano_blueprint, "get_db", connection)
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    app.register_blueprint(banano_blueprint.ban_bp)

    def tip(_request_number):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = 1
            return client.post(
                "/ban/tip", json={"to_agent": "bob", "amount": 8}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(tip, (1, 2)))

    for db in connections:
        db.close()
    verify = sqlite3.connect(db_path)
    sent = verify.execute(
        "SELECT COALESCE(SUM(amount_ban),0) FROM ban_transactions "
        "WHERE agent_id=1 AND tx_type='tip_sent' AND status='credited'"
    ).fetchone()[0]
    received = verify.execute(
        "SELECT COALESCE(SUM(amount_ban),0) FROM ban_transactions "
        "WHERE agent_id=2 AND tx_type='tip_received' AND status='credited'"
    ).fetchone()[0]
    verify.close()

    assert sorted(statuses) == [200, 400]
    assert sent == 8.0
    assert received == 8.0
