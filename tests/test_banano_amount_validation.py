# SPDX-License-Identifier: MIT
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
        now = time.time()
        db.executemany(
            "INSERT INTO agents (id, agent_name) VALUES (?, ?)",
            [(1, "alice"), (2, "bob")],
        )
        db.execute(
            "INSERT INTO videos (video_id, agent_id) VALUES (?, ?)",
            ("video-1", 1),
        )
        db.execute(
            """
            INSERT INTO ban_transactions
            (agent_id, tx_type, amount_ban, reason, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, "reward", 10.0, "seed_balance", "credited", now),
        )
        db.commit()

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    client.db_path = db_path
    return client


def _ban_transaction_count(db_path):
    with sqlite3.connect(db_path) as db:
        return db.execute("SELECT COUNT(*) FROM ban_transactions").fetchone()[0]


@pytest.mark.parametrize("amount", ["abc", "NaN", "Infinity", True, 0, -1])
def test_ban_tip_rejects_invalid_amounts_without_writes(ban_client, amount):
    before = _ban_transaction_count(ban_client.db_path)

    response = ban_client.post("/ban/tip", json={"to_agent": "bob", "amount": amount})

    assert response.status_code == 400
    assert response.get_json()["error"] == "amount must be a finite positive number"
    assert _ban_transaction_count(ban_client.db_path) == before


@pytest.mark.parametrize("amount", ["abc", "NaN", "Infinity", True, 0, -1])
def test_ban_withdraw_rejects_invalid_amounts_without_writes(ban_client, amount):
    before = _ban_transaction_count(ban_client.db_path)

    response = ban_client.post(
        "/ban/withdraw",
        json={"address": "ban_" + "a" * 60, "amount": amount},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "amount must be a finite positive number"
    assert _ban_transaction_count(ban_client.db_path) == before


def test_ban_tip_rejects_non_object_json_body(ban_client):
    before = _ban_transaction_count(ban_client.db_path)

    response = ban_client.post("/ban/tip", json=["not", "an", "object"])

    assert response.status_code == 400
    assert response.get_json()["error"] == "JSON object required"
    assert _ban_transaction_count(ban_client.db_path) == before


def test_valid_ban_tip_still_records_sender_and_recipient_rows(ban_client):
    response = ban_client.post("/ban/tip", json={"to_agent": "bob", "amount": "1.25"})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "amount_ban": 1.25, "to": "bob"}

    with sqlite3.connect(ban_client.db_path) as db:
        rows = db.execute(
            """
            SELECT agent_id, tx_type, amount_ban, status
            FROM ban_transactions
            ORDER BY id
            """
        ).fetchall()

    assert rows == [
        (1, "reward", 10.0, "credited"),
        (1, "tip_sent", 1.25, "credited"),
        (2, "tip_received", 1.25, "credited"),
    ]


def test_ban_video_generation_reward_rejects_non_object_json(ban_client):
    before = _ban_transaction_count(ban_client.db_path)

    response = ban_client.post("/ban/reward-video-gen", json=["not", "an", "object"])

    assert response.status_code == 400
    assert response.get_json()["error"] == "JSON object required"
    assert _ban_transaction_count(ban_client.db_path) == before


@pytest.mark.parametrize("field", ["agent_name", "video_id", "gen_method"])
def test_ban_video_generation_reward_rejects_non_string_fields(ban_client, field):
    before = _ban_transaction_count(ban_client.db_path)
    payload = {
        "agent_name": "alice",
        "video_id": "video-1",
        "gen_method": "text",
    }
    payload[field] = ["not", "a", "string"]

    response = ban_client.post("/ban/reward-video-gen", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == f"{field} must be a string"
    assert _ban_transaction_count(ban_client.db_path) == before


@pytest.mark.parametrize("query", ["limit=0", "limit=-1", "offset=-1"])
def test_ban_transactions_rejects_non_positive_pagination(ban_client, query):
    response = ban_client.get(f"/ban/transactions/alice?{query}")

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid pagination parameters"


def test_valid_ban_video_generation_reward_still_records_reward(ban_client):
    response = ban_client.post(
        "/ban/reward-video-gen",
        json={"agent_name": "alice", "video_id": "video-1", "gen_method": "text"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "amount_ban": 2.0,
        "gen_method": "text",
        "reason": "AI video generation (text)",
        "video_id": "video-1",
    }

    with sqlite3.connect(ban_client.db_path) as db:
        rows = db.execute(
            """
            SELECT agent_id, tx_type, amount_ban, reason, video_id, status
            FROM ban_transactions
            ORDER BY id
            """
        ).fetchall()

    assert rows == [
        (1, "reward", 10.0, "seed_balance", "", "credited"),
        (1, "reward", 2.0, "video_gen_text", "video-1", "credited"),
    ]
