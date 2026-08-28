# SPDX-License-Identifier: MIT
"""Validation tests for SocketIO chat handlers."""

import importlib
import sqlite3
import sys
import types

from flask import Flask


def _init_chat_db(db_path):
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE chat_bans (
                video_id TEXT,
                user_id TEXT,
                expires_at REAL
            );
            CREATE TABLE chat_messages (
                id TEXT,
                video_id TEXT,
                user_id TEXT,
                username TEXT,
                message TEXT,
                is_super INTEGER,
                tip_amount REAL,
                created_at REAL
            );
            """
        )


def _table_count(db_path, table_name):
    with sqlite3.connect(db_path) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def _load_websocket_server(monkeypatch):
    events = []

    class FakeSocketIO:
        def on(self, _event):
            def _decorator(func):
                return func

            return _decorator

        def init_app(self, *_args, **_kwargs):
            pass

    fake_socketio = types.SimpleNamespace(
        SocketIO=FakeSocketIO,
        emit=lambda *args, **kwargs: events.append((args, kwargs)),
        join_room=lambda *_args, **_kwargs: None,
        leave_room=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "flask_socketio", fake_socketio)
    sys.modules.pop("websocket_server", None)
    module = importlib.import_module("websocket_server")
    sys.modules.pop("websocket_server", None)
    return module, events


def test_chat_message_rejects_non_string_message(monkeypatch):
    websocket_server, events = _load_websocket_server(monkeypatch)

    websocket_server.on_chat_message(
        {
            "video_id": "video-1",
            "username": "alice",
            "user_id": "user-1",
            "message": 123,
        }
    )

    assert events == [
        (("error", {"message": "Message must be 1-500 characters"}), {})
    ]


def test_chat_message_accepts_valid_string_message(monkeypatch, tmp_path):
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = Flask(__name__)
    app.config["CHAT_DB_PATH"] = str(db_path)
    websocket_server._last_message_time.clear()

    with app.app_context():
        websocket_server.on_chat_message(
            {
                "video_id": "video-1",
                "username": "alice",
                "user_id": "user-1",
                "message": "  hello  ",
            }
        )

    assert events[-1][0][0] == "new_message"
    assert events[-1][0][1]["message"] == "hello"
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT message FROM chat_messages WHERE video_id = ?",
            ("video-1",),
        ).fetchone()
    assert row == ("hello",)


def test_chat_message_rejects_non_object_event(monkeypatch):
    websocket_server, events = _load_websocket_server(monkeypatch)

    websocket_server.on_chat_message(["not", "an", "object"])

    assert events == [(("error", {"message": "Event data must be an object"}), {})]


def test_chat_message_rejects_malformed_numeric_fields_without_insert(
    monkeypatch, tmp_path
):
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = Flask(__name__)
    app.config["CHAT_DB_PATH"] = str(db_path)
    websocket_server._last_message_time.clear()

    with app.app_context():
        websocket_server.on_chat_message(
            {
                "video_id": "video-1",
                "username": "alice",
                "user_id": "user-1",
                "message": "hello",
                "tip_amount": "oops",
            }
        )

    assert events == [
        (("error", {"message": "tip_amount must be a finite non-negative number"}), {})
    ]
    assert _table_count(db_path, "chat_messages") == 0
    assert websocket_server._last_message_time == {}


def test_super_chat_rejects_malformed_tip_without_insert(monkeypatch, tmp_path):
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = Flask(__name__)
    app.config["CHAT_DB_PATH"] = str(db_path)
    websocket_server._last_message_time.clear()

    with app.app_context():
        websocket_server.on_super_chat(
            {
                "video_id": "video-1",
                "username": "alice",
                "user_id": "user-1",
                "message": "boost",
                "tip_amount": "nan",
            }
        )

    assert events == [
        (("error", {"message": "tip_amount must be a finite positive number"}), {})
    ]
    assert _table_count(db_path, "chat_messages") == 0
    assert websocket_server._last_message_time == {}


def test_mod_action_rejects_malformed_ban_duration_without_insert(
    monkeypatch, tmp_path
):
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = Flask(__name__)
    app.config["CHAT_DB_PATH"] = str(db_path)

    with app.app_context():
        websocket_server.on_mod_action(
            {
                "action": "ban",
                "video_id": "video-1",
                "target_user_id": "user-1",
                "duration": "later",
            }
        )

    assert events == [
        (("error", {"message": "duration must be a finite non-negative number"}), {})
    ]
    assert _table_count(db_path, "chat_bans") == 0


def test_mod_action_rejects_malformed_timeout_duration(monkeypatch):
    websocket_server, events = _load_websocket_server(monkeypatch)
    websocket_server._last_message_time.clear()

    websocket_server.on_mod_action(
        {
            "action": "timeout",
            "video_id": "video-1",
            "target_user_id": "user-1",
            "duration": "later",
        }
    )

    assert events == [
        (("error", {"message": "duration must be a finite non-negative number"}), {})
    ]
    assert websocket_server._last_message_time == {}
