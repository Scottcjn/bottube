# SPDX-License-Identifier: MIT
"""Regression tests for Banano tip video_id and JSON body validation."""

import sqlite3
import time

import pytest
from flask import Flask, g

import banano_blueprint


@pytest.fixture()
def ban_client(tmp_path):
    db_path = tmp_path / "bottube.db"
    app = Flask(__name__)
    app.secret_key = "test-secret-key"
    app.config["TESTING"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False
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
        db.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, agent_name TEXT UNIQUE NOT NULL)")
        db.execute("CREATE TABLE videos (video_id TEXT PRIMARY KEY, agent_id INTEGER NOT NULL)")
        banano_blueprint.init_ban_tables(db)
        now = time.time()
        db.executemany(
            "INSERT INTO agents (id, agent_name) VALUES (?, ?)",
            [(1, "alice"), (2, "bob")],
        )
        db.execute("INSERT INTO videos (video_id, agent_id) VALUES (?, ?)", ("video-1", 1))
        db.execute(
            "INSERT INTO ban_transactions (agent_id, tx_type, amount_ban, reason, status, created_at) "
            "VALUES (?, 'reward', ?, 'seed_balance', 'credited', ?)",
            (1, 10.0, now),
        )
        db.commit()

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    client.db_path = db_path
    return client


def _tx_count(db_path):
    with sqlite3.connect(db_path) as db:
        return db.execute("SELECT COUNT(*) FROM ban_transactions").fetchone()[0]


@pytest.mark.parametrize("video_id", [{"id": "video-1"}, ["video-1"], 123, True])
def test_ban_tip_rejects_non_string_video_id_without_writes(ban_client, video_id):
    before = _tx_count(ban_client.db_path)

    response = ban_client.post(
        "/ban/tip",
        json={"to_agent": "bob", "amount": 1.0, "video_id": video_id},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "video_id must be a string"}
    assert _tx_count(ban_client.db_path) == before


@pytest.mark.parametrize("payload", [False, 0, "", ["not-an-object"]])
def test_ban_endpoints_reject_falsy_and_non_object_json_bodies(ban_client, monkeypatch, payload):
    monkeypatch.setattr(banano_blueprint, "ADMIN_KEY", "test-admin")
    before = _tx_count(ban_client.db_path)

    tip_resp = ban_client.post("/ban/tip", json=payload)
    assert tip_resp.status_code == 400
    assert tip_resp.get_json() == {"error": "JSON object required"}

    gen_resp = ban_client.post(
        "/ban/reward-video-gen",
        json=payload,
        headers={"X-Admin-Key": "test-admin"},
    )
    assert gen_resp.status_code == 400
    assert gen_resp.get_json() == {"error": "JSON object required"}
    assert _tx_count(ban_client.db_path) == before


def test_ban_tip_normalizes_string_and_null_video_id(ban_client):
    resp_trimmed = ban_client.post(
        "/ban/tip",
        json={"to_agent": "bob", "amount": 1.5, "video_id": "  video-1  "},
    )
    assert resp_trimmed.status_code == 200

    resp_null = ban_client.post(
        "/ban/tip",
        json={"to_agent": "bob", "amount": 0.5, "video_id": None},
    )
    assert resp_null.status_code == 200

    with sqlite3.connect(ban_client.db_path) as db:
        rows = db.execute(
            "SELECT tx_type, video_id FROM ban_transactions WHERE tx_type = 'tip_sent' ORDER BY id"
        ).fetchall()
    assert rows == [("tip_sent", "video-1"), ("tip_sent", "")]
