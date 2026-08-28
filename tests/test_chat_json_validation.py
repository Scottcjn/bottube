# SPDX-License-Identifier: MIT
"""Regression tests validating JSON parsing and type safety on chat routes (#1780)."""
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
    db_path = tmp_path / "chat_val.db"

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


def test_send_message_rejects_malformed_fields(chat_client):
    # message not a string
    resp = chat_client.post("/api/chat/video-1/send", json={"message": 42})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Message must be a string"}

    # invalid tip_amount (string)
    resp = chat_client.post("/api/chat/video-1/send", json={"message": "hello", "tip_amount": "oops"})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Invalid tip_amount"}

    # invalid tip_amount (boolean)
    resp = chat_client.post("/api/chat/video-1/send", json={"message": "hello", "tip_amount": True})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Invalid tip_amount"}

    # valid message
    resp = chat_client.post("/api/chat/video-1/send", json={"message": "hello world", "tip_amount": 0.5})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "sent"
    assert _chat_message_count(chat_client.db_path) == 1


def test_ban_user_validation(chat_client):
    # without mod session -> 403
    resp = chat_client.post("/api/chat/video-1/ban", json={"user_id": "u1", "duration": "later"})
    assert resp.status_code == 403

    with chat_client.session_transaction() as sess:
        sess["is_mod"] = True
        sess["username"] = "moderator"

    # invalid duration string
    resp = chat_client.post("/api/chat/video-1/ban", json={"user_id": "u1", "duration": "later"})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Invalid duration"}

    # valid ban
    resp = chat_client.post("/api/chat/video-1/ban", json={"user_id": "u1", "duration": 3600})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "banned"


def test_chat_settings_validation(chat_client):
    with chat_client.session_transaction() as sess:
        sess["is_mod"] = True

    # invalid slow_mode string
    resp = chat_client.post("/api/chat/video-1/settings", json={"slow_mode": "fast"})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Invalid slow_mode"}

    # valid settings
    resp = chat_client.post("/api/chat/video-1/settings", json={"slow_mode": 10, "sub_only": 1})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "updated"
