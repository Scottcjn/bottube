# SPDX-License-Identifier: MIT
"""Validation tests for SocketIO chat handlers."""

import importlib
import sqlite3
import sys
import types

from flask import Flask


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
