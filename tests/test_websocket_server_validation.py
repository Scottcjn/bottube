# SPDX-License-Identifier: MIT
"""Validation tests for SocketIO chat handlers."""

import importlib
import sqlite3
import sys
import types

from flask import Flask


def _load_websocket_server(monkeypatch):
    events = []
    room_actions = []

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
        join_room=lambda *args, **kwargs: room_actions.append(("join", args, kwargs)),
        leave_room=lambda *args, **kwargs: room_actions.append(("leave", args, kwargs)),
    )
    monkeypatch.setitem(sys.modules, "flask_socketio", fake_socketio)
    sys.modules.pop("websocket_server", None)
    module = importlib.import_module("websocket_server")
    sys.modules.pop("websocket_server", None)
    return module, events, room_actions


def test_chat_message_rejects_non_string_message(monkeypatch):
    websocket_server, events, _room_actions = _load_websocket_server(monkeypatch)

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
    websocket_server, events, _room_actions = _load_websocket_server(monkeypatch)
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
            CREATE TABLE videos (video_id TEXT PRIMARY KEY);
            INSERT INTO videos (video_id) VALUES ('video-1');
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


def test_chat_message_rejects_non_finite_tip(monkeypatch):
    websocket_server, events, _room_actions = _load_websocket_server(monkeypatch)
    app = Flask(__name__)
    websocket_server._last_message_time.clear()

    with app.app_context():
        websocket_server.on_chat_message(
            {
                "video_id": "video-1",
                "username": "alice",
                "user_id": "user-1",
                "message": "hello",
                "tip_amount": float("nan"),
            }
        )

    assert events == [
        (("error", {"message": "tip_amount must be a finite non-negative number"}), {})
    ]


def test_super_chat_rejects_zero_tip(monkeypatch):
    websocket_server, events, _room_actions = _load_websocket_server(monkeypatch)

    websocket_server.on_super_chat(
        {
            "video_id": "video-1",
            "username": "alice",
            "user_id": "user-1",
            "message": "hello",
            "tip_amount": 0,
        }
    )

    assert events == [
        (("error", {"message": "tip_amount must be a finite positive number"}), {})
    ]


def test_mod_action_timeout_rejects_non_numeric_duration(monkeypatch):
    websocket_server, events, _room_actions = _load_websocket_server(monkeypatch)

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


def _create_chat_db(db_path):
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE videos (video_id TEXT PRIMARY KEY);
            INSERT INTO videos (video_id) VALUES ('video-1');
            CREATE TABLE chat_bans (
                id TEXT,
                video_id TEXT,
                user_id TEXT,
                banned_by TEXT,
                reason TEXT,
                expires_at REAL,
                created_at REAL
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


def test_chat_message_rejects_missing_video_without_persisting(monkeypatch, tmp_path):
    websocket_server, events, _room_actions = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _create_chat_db(db_path)
    app = Flask(__name__)
    app.config["CHAT_DB_PATH"] = str(db_path)
    websocket_server._last_message_time.clear()

    with app.app_context():
        websocket_server.on_chat_message(
            {
                "video_id": "ghost-video",
                "username": "alice",
                "user_id": "ghost-user",
                "message": "hello",
            }
        )

    assert events[-1] == (("error", {"message": "Video not found"}), {})
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM chat_messages").fetchone() == (0,)


def test_join_and_leave_reject_missing_video_without_room_action(monkeypatch, tmp_path):
    websocket_server, events, room_actions = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _create_chat_db(db_path)
    app = Flask(__name__)
    app.config["CHAT_DB_PATH"] = str(db_path)

    with app.app_context():
        websocket_server.on_join({"video_id": "ghost-video", "username": "alice"})
        websocket_server.on_leave({"video_id": "ghost-video", "username": "alice"})

    assert room_actions == []
    assert events == [
        (("error", {"message": "Video not found"}), {}),
        (("error", {"message": "Video not found"}), {}),
    ]


def test_mod_action_rejects_missing_video_without_mutating(monkeypatch, tmp_path):
    websocket_server, events, _room_actions = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _create_chat_db(db_path)
    app = Flask(__name__)
    app.config["CHAT_DB_PATH"] = str(db_path)

    with app.app_context():
        websocket_server.on_mod_action(
            {
                "action": "ban",
                "video_id": "ghost-video",
                "target_user_id": "user-1",
            }
        )

    assert events == [(("error", {"message": "Video not found"}), {})]
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM chat_bans").fetchone() == (0,)
