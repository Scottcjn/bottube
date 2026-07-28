# SPDX-License-Identifier: MIT
"""/ban/tip must count pending withdrawals against the spendable balance.

Withdrawal rows are written with ``status='pending'`` and only ever move to
``'sent'``/``'failed'``.  ``ban_tip`` filtered on ``status = 'credited'``
*before* its CASE expression, so withdrawal rows dropped out of the sum
entirely and already-withdrawn BAN stayed tippable -- a ledger double-spend.
``ban_withdraw`` gets this right with ``status IN ('credited','sent','pending')``.
"""

import sqlite3
import time
from importlib import metadata

import pytest
import werkzeug
from flask import Flask, g

import banano_blueprint


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


@pytest.fixture
def ban_client(tmp_path):
    db_path = tmp_path / "bottube.db"
    app = Flask(__name__)
    app.secret_key = "test-secret-key"
    app.config["TESTING"] = True
    app.register_blueprint(banano_blueprint.ban_bp)

    @app.before_request
    def before_request():
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row

    @app.teardown_request
    def teardown_request(_exc):
        db = getattr(g, "db", None)
        if db is not None:
            db.close()

    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE agents (id INTEGER PRIMARY KEY, agent_name TEXT UNIQUE NOT NULL)"
        )
        db.execute(
            "CREATE TABLE videos (video_id TEXT PRIMARY KEY, agent_id INTEGER NOT NULL)"
        )
        banano_blueprint.init_ban_tables(db)
        db.executemany(
            "INSERT INTO agents (id, agent_name) VALUES (?, ?)",
            [(1, "alice"), (2, "bob")],
        )
        db.execute(
            """
            INSERT INTO ban_transactions
            (agent_id, tx_type, amount_ban, reason, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, "reward", 10.0, "seed_balance", "credited", time.time()),
        )
        db.commit()

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    client.db_path = db_path
    return client


def _pending_withdrawal_total(db_path):
    with sqlite3.connect(db_path) as db:
        return db.execute(
            "SELECT COALESCE(SUM(amount_ban), 0) FROM ban_transactions "
            "WHERE tx_type = 'withdrawal' AND status = 'pending'"
        ).fetchone()[0]


def test_tip_rejected_after_full_balance_is_withdrawn(ban_client):
    """Alice earns 10 BAN, withdraws all 10, then must not be able to tip it."""
    withdraw = ban_client.post(
        "/ban/withdraw",
        json={"amount": 10.0, "address": "ban_" + "1" * 60},
    )
    assert withdraw.status_code == 200, withdraw.get_json()
    assert _pending_withdrawal_total(ban_client.db_path) == 10.0

    # The same 10 BAN is already committed to a payout row.
    tip = ban_client.post("/ban/tip", json={"to_agent": "bob", "amount": 10.0})

    assert tip.status_code == 400, tip.get_json()
    assert "Insufficient BAN balance" in tip.get_json()["error"]
    # And no second payout obligation was created.
    assert _pending_withdrawal_total(ban_client.db_path) == 10.0


def test_tip_still_allowed_within_the_unwithdrawn_remainder(ban_client):
    """Control: withdrawing part of the balance leaves the rest tippable."""
    withdraw = ban_client.post(
        "/ban/withdraw",
        json={"amount": 6.0, "address": "ban_" + "1" * 60},
    )
    assert withdraw.status_code == 200, withdraw.get_json()

    tip = ban_client.post("/ban/tip", json={"to_agent": "bob", "amount": 4.0})
    assert tip.status_code == 200, tip.get_json()
