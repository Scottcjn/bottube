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
    return _table_count(db_path, "chat_messages")


def _chat_ban_count(db_path):
    return _table_count(db_path, "chat_bans")


def _table_count(db_path, table_name):
    with sqlite3.connect(db_path) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def _chat_settings_row(db_path, video_id):
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT slow_mode, sub_only, premiere FROM chat_settings WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        return dict(row) if row else None


def _make_moderator(client):
    with client.session_transaction() as sess:
        sess["is_mod"] = True
        sess["username"] = "mod"


def test_send_message_rejects_non_object_json_without_insert(chat_client):
    resp = chat_client.post("/api/chat/video-1/send", json=["not", "an", "object"])

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON object required"}
    assert _chat_message_count(chat_client.db_path) == 0


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"username": "Ada", "message": 42}, "message must be a string"),
        (
            {"username": "Ada", "message": "Hello chat", "is_super": "boost"},
            "is_super must be 0/1 or boolean",
        ),
        (
            {"username": "Ada", "message": "Hello chat", "tip_amount": "oops"},
            "tip_amount must be a finite non-negative number",
        ),
        (
            {"username": "Ada", "message": "Hello chat", "tip_amount": "nan"},
            "tip_amount must be a finite non-negative number",
        ),
        (
            {"username": "Ada", "message": "Hello chat", "tip_amount": -1},
            "tip_amount must be a finite non-negative number",
        ),
    ],
)
def test_send_message_rejects_malformed_fields_without_insert(
    chat_client, payload, expected_error
):
    resp = chat_client.post("/api/chat/video-1/send", json=payload)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": expected_error}
    assert _chat_message_count(chat_client.db_path) == 0


def test_send_message_still_records_valid_json_object(chat_client):
    resp = chat_client.post(
        "/api/chat/video-1/send",
        json={"username": "Ada", "message": "Hello chat"},
    )

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "sent"
    assert _chat_message_count(chat_client.db_path) == 1


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        (["not", "an", "object"], "JSON object required"),
        ({"user_id": 123}, "user_id must be a string"),
        ({"user_id": ""}, "user_id is required"),
        (
            {"user_id": "victim", "duration": "later"},
            "duration must be a finite non-negative number",
        ),
        (
            {"user_id": "victim", "duration": -1},
            "duration must be a finite non-negative number",
        ),
    ],
)
def test_ban_user_rejects_malformed_json_without_insert(
    chat_client, payload, expected_error
):
    _make_moderator(chat_client)

    resp = chat_client.post("/api/chat/video-1/ban", json=payload)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": expected_error}
    assert _chat_ban_count(chat_client.db_path) == 0


def test_ban_user_still_accepts_valid_duration(chat_client):
    _make_moderator(chat_client)

    resp = chat_client.post(
        "/api/chat/video-1/ban",
        json={"user_id": " victim ", "duration": 60, "reason": "spam"},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "banned"}
    assert _chat_ban_count(chat_client.db_path) == 1


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        (["not", "an", "object"], "JSON object required"),
        (
            {"slow_mode": "fast"},
            "slow_mode, sub_only, and premiere must be 0/1 or boolean",
        ),
        (
            {"slow_mode": 2, "sub_only": 0, "premiere": 1},
            "slow_mode, sub_only, and premiere must be 0/1 or boolean",
        ),
        (
            {"sub_only": "maybe"},
            "slow_mode, sub_only, and premiere must be 0/1 or boolean",
        ),
        (
            {"premiere": "soon"},
            "slow_mode, sub_only, and premiere must be 0/1 or boolean",
        ),
        (
            {"premiere_at": "soon"},
            "premiere_at must be a finite non-negative number",
        ),
    ],
)
def test_chat_settings_rejects_malformed_json_without_update(
    chat_client, payload, expected_error
):
    _make_moderator(chat_client)

    resp = chat_client.post("/api/chat/video-1/settings", json=payload)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": expected_error}
    assert _chat_settings_row(chat_client.db_path, "video-1") is None


def test_chat_settings_still_accepts_valid_numeric_strings_and_booleans(chat_client):
    _make_moderator(chat_client)

    resp = chat_client.post(
        "/api/chat/video-1/settings",
        json={"slow_mode": True, "sub_only": 0, "premiere": 1},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "updated"}
    assert _chat_settings_row(chat_client.db_path, "video-1") == {
        "slow_mode": 1,
        "sub_only": 0,
        "premiere": 1,
    }
