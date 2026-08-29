# SPDX-License-Identifier: MIT
import sqlite3
from importlib import metadata

import pytest
import werkzeug
from flask import Flask, g

import chat_handlers

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


@pytest.fixture()
def chat_client(tmp_path):
    db_path = tmp_path / "chat.db"

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["DATABASE"] = str(db_path)
    app.config["SECRET_KEY"] = "test-secret"
    app.register_blueprint(chat_handlers.chat_bp)

    @app.teardown_request
    def teardown_request(_exc):
        db = getattr(g, "db", None)
        if db is not None:
            db.close()
            g.db = None

    with app.app_context():
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        g.db = db
        chat_handlers.init_chat_tables(db)

    client = app.test_client()
    client.db_path = db_path
    return client


def _chat_message_count(db_path):
    with sqlite3.connect(db_path) as db:
        return db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]


def test_send_message_rejects_non_object_json_without_insert(chat_client):
    resp = chat_client.post("/api/chat/video-1/send", json=["not", "an", "object"])

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON object required"}
    assert _chat_message_count(chat_client.db_path) == 0


def test_send_message_still_records_valid_json_object(chat_client):
    resp = chat_client.post(
        "/api/chat/video-1/send",
        json={"username": "Ada", "message": "Hello chat"},
    )

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "sent"
    assert _chat_message_count(chat_client.db_path) == 1


def test_send_message_rejects_non_finite_tip_without_insert(chat_client):
    resp = chat_client.post(
        "/api/chat/video-1/send",
        json={"username": "Ada", "message": "Hello chat", "tip_amount": float("inf")},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "tip_amount must be a finite non-negative number"}
    assert _chat_message_count(chat_client.db_path) == 0


def test_ban_rejects_non_numeric_duration(chat_client):
    with chat_client.session_transaction() as sess:
        sess["is_mod"] = True
        sess["username"] = "mod"
    resp = chat_client.post(
        "/api/chat/video-1/ban",
        json={"user_id": "user-1", "duration": "forever"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "duration must be a finite non-negative number"}


def test_settings_reject_non_boolean_like_flags(chat_client):
    with chat_client.session_transaction() as sess:
        sess["is_mod"] = True
    resp = chat_client.post(
        "/api/chat/video-1/settings",
        json={"slow_mode": 2, "sub_only": 0, "premiere": 1},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "slow_mode, sub_only, and premiere must be 0/1 or boolean"}
