# SPDX-License-Identifier: MIT
"""Validation tests for SocketIO chat handlers."""

import importlib
import sqlite3
import sys
import types

from flask import Flask, session


def _init_chat_db(db_path):
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_bans (
                id TEXT,
                video_id TEXT,
                user_id TEXT,
                banned_by TEXT,
                reason TEXT,
                expires_at REAL,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT,
                video_id TEXT,
                user_id TEXT,
                username TEXT,
                message TEXT,
                is_super INTEGER,
                tip_amount REAL,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                api_key TEXT UNIQUE NOT NULL,
                created_at REAL NOT NULL DEFAULT 0.0
            );
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE NOT NULL,
                agent_id INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL DEFAULT 'Video',
                is_removed INTEGER DEFAULT 0
            );
            INSERT OR IGNORE INTO agents (id, agent_name, display_name, api_key) VALUES (1, 'owner-user', 'Owner', 'key-owner');
            INSERT OR IGNORE INTO videos (video_id, agent_id) VALUES ('video-1', 1);
            """
        )


def _table_count(db_path, table_name):
    with sqlite3.connect(db_path) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def _create_app(db_path=None):
    app = Flask(__name__)
    app.secret_key = "test-secret-key"
    if db_path:
        app.config["CHAT_DB_PATH"] = str(db_path)
    return app


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
    app = _create_app()
    with app.test_request_context():
        session["user_id"] = "user-1"
        session["username"] = "alice"
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

    app = _create_app(db_path)
    websocket_server._last_message_time.clear()

    with app.test_request_context():
        session["user_id"] = "user-1"
        session["username"] = "alice"
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

    app = _create_app(db_path)
    websocket_server._last_message_time.clear()

    with app.test_request_context():
        session["user_id"] = "user-1"
        session["username"] = "alice"
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

    app = _create_app(db_path)
    websocket_server._last_message_time.clear()

    with app.test_request_context():
        session["user_id"] = "user-1"
        session["username"] = "alice"
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

    app = _create_app(db_path)

    with app.test_request_context():
        session["user_id"] = "user-1"
        session["username"] = "alice"
        session["is_mod"] = True
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


def test_mod_action_rejects_malformed_timeout_duration(monkeypatch, tmp_path):
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = _create_app(db_path)
    websocket_server._last_message_time.clear()

    with app.test_request_context():
        session["user_id"] = "user-1"
        session["username"] = "alice"
        session["is_mod"] = True
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


def test_leave_rejects_missing_video_without_room_action(monkeypatch, tmp_path):
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = _create_app(db_path)

    with app.test_request_context():
        session["user_id"] = "user-1"
        session["username"] = "alice"
        websocket_server.on_leave({"video_id": "ghost-video", "username": "alice"})

    assert events == [(("error", {"message": "Video not found"}), {})]


def test_leave_accepts_existing_video(monkeypatch, tmp_path):
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = _create_app(db_path)

    with app.test_request_context():
        session["user_id"] = "user-1"
        session["username"] = "alice"
        websocket_server.on_leave({"video_id": "video-1", "username": "alice"})

    assert events == [
        (("system", {"message": "alice left the chat", "type": "leave"}), {"room": "video-1"})
    ]


def test_mod_action_ban_rejects_missing_video_without_insert(monkeypatch, tmp_path):
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = _create_app(db_path)

    with app.test_request_context():
        session["user_id"] = "user-1"
        session["username"] = "alice"
        session["is_mod"] = True
        websocket_server.on_mod_action(
            {
                "action": "ban",
                "video_id": "ghost-video",
                "target_user_id": "user-1",
                "mod_name": "mod",
                "reason": "spam",
            }
        )

    assert events == [(("error", {"message": "Video not found"}), {})]
    assert _table_count(db_path, "chat_bans") == 0


def test_mod_action_ban_accepts_existing_video(monkeypatch, tmp_path):
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = _create_app(db_path)

    with app.test_request_context():
        session["user_id"] = "user-1"
        session["username"] = "alice"
        session["is_mod"] = True
        websocket_server.on_mod_action(
            {
                "action": "ban",
                "video_id": "video-1",
                "target_user_id": "user-1",
                "mod_name": "mod",
                "reason": "spam",
            }
        )

    assert any(
        (("system", {"message": "User banned by moderator", "type": "ban"}), {"room": "video-1"})
        == item
        for item in events
    )
    assert _table_count(db_path, "chat_bans") == 1


# ── Issue #2274 Regression Tests ───────────────────────────────

def test_unauthenticated_websocket_event_rejected(monkeypatch, tmp_path):
    """Ensure unauthenticated WebSocket events are rejected with error."""
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = _create_app(db_path)

    with app.test_request_context():
        websocket_server.on_chat_message({"video_id": "video-1", "message": "hello"})
        websocket_server.on_mod_action({"action": "ban", "video_id": "video-1", "target_user_id": "user-1"})

    assert len(events) == 2
    assert events[0] == (("error", {"message": "Authentication required"}), {})
    assert events[1] == (("error", {"message": "Authentication required"}), {})


def test_payload_identity_spoofing_rejected(monkeypatch, tmp_path):
    """Ensure client cannot spoof user_id or username in payload."""
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = _create_app(db_path)

    with app.test_request_context():
        session["user_id"] = "real-user"
        session["username"] = "real_name"
        websocket_server.on_chat_message({
            "video_id": "video-1",
            "user_id": "fake-user",
            "username": "real_name",
            "message": "spoof test"
        })

    assert len(events) == 1
    assert events[0][0][0] == "error"
    assert "spoofing" in events[0][0][1]["message"].lower() or "mismatch" in events[0][0][1]["message"].lower()


def test_cookie_and_api_key_give_same_user_id(monkeypatch, tmp_path):
    """Ensure cookie session (session['user_id'] = agents.id) and API key produce identical user_id."""
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = _create_app(db_path)

    # Insert agent with id=42, agent_name='alice', display_name='Alice Agent', api_key='key-alice'
    with sqlite3.connect(db_path) as db:
        db.execute(
            "INSERT INTO agents (id, agent_name, display_name, api_key) VALUES (42, 'alice', 'Alice Agent', 'key-alice')"
        )

    # 1. Cookie path (real login sets session["user_id"] = 42)
    with app.test_request_context():
        session["user_id"] = 42
        auth_cookie = websocket_server._get_authenticated_user({}, app)

    # 2. API key path
    with app.test_request_context(headers={"X-API-Key": "key-alice"}):
        auth_apikey = websocket_server._get_authenticated_user({}, app)

    assert auth_cookie is not None
    assert auth_apikey is not None
    assert auth_cookie["user_id"] == "42"
    assert auth_apikey["user_id"] == "42"
    assert auth_cookie["username"] == "Alice Agent"
    assert auth_apikey["username"] == "Alice Agent"


def test_banned_agent_rejected_on_api_key_path(monkeypatch, tmp_path):
    """Ensure banned agents are rejected on the API-key path like require_api_key does."""
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    # Add is_banned column and insert a banned agent
    with sqlite3.connect(db_path) as db:
        try:
            db.execute("ALTER TABLE agents ADD COLUMN is_banned INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        db.execute(
            "INSERT INTO agents (id, agent_name, api_key, is_banned) VALUES (99, 'banned-agent', 'key-banned', 1)"
        )

    app = _create_app(db_path)

    with app.test_request_context(headers={"X-API-Key": "key-banned"}):
        auth_user = websocket_server._get_authenticated_user({}, app)

    assert auth_user is None


def test_mod_action_rejected_for_non_mod_non_owner(monkeypatch, tmp_path):
    """Ensure mod_action is rejected when user is neither channel owner nor platform mod."""
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    with sqlite3.connect(db_path) as db:
        db.execute(
            "INSERT INTO agents (id, agent_name, api_key) VALUES (10, 'regular-agent', 'key-reg')"
        )

    app = _create_app(db_path)

    with app.test_request_context():
        session["user_id"] = 10  # Real login session user_id integer
        websocket_server.on_mod_action({
            "action": "ban",
            "video_id": "video-1",
            "target_user_id": "target-user"
        })

    assert len(events) == 1
    assert events[0] == (("error", {"message": "Moderator or channel owner authorization required"}), {})
    assert _table_count(db_path, "chat_bans") == 0


def test_mod_action_accepted_for_channel_owner(monkeypatch, tmp_path):
    """Ensure mod_action succeeds for channel owner (videos.agent_id == agents.id)."""
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    app = _create_app(db_path)

    # Video 'video-1' has agent_id=1, which matches agent id=1 ('owner-user')
    with app.test_request_context():
        session["user_id"] = 1  # Real login session user_id (agents.id = 1)
        websocket_server.on_mod_action({
            "action": "ban",
            "video_id": "video-1",
            "target_user_id": "target-user",
            "reason": "owner ban"
        })

    assert _table_count(db_path, "chat_bans") == 1


def test_mod_action_accepted_for_platform_mod(monkeypatch, tmp_path):
    """Ensure mod_action succeeds for platform moderator when agents table has is_mod=1."""
    websocket_server, events = _load_websocket_server(monkeypatch)
    db_path = tmp_path / "chat.db"
    _init_chat_db(db_path)

    with sqlite3.connect(db_path) as db:
        try:
            db.execute("ALTER TABLE agents ADD COLUMN is_mod INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        db.execute(
            "INSERT INTO agents (id, agent_name, api_key, is_mod) VALUES (55, 'mod-agent', 'key-mod', 1)"
        )

    app = _create_app(db_path)

    with app.test_request_context():
        session["user_id"] = 55  # Real login session user_id (agents.id = 55)
        websocket_server.on_mod_action({
            "action": "ban",
            "video_id": "video-1",
            "target_user_id": "target-user-2",
            "reason": "mod ban"
        })

    assert _table_count(db_path, "chat_bans") == 1
