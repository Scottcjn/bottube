"""Security regressions for the dormant Socket.IO chat layer.

These cases pin the authorization contract required before init_socketio() is
wired into production. They exercise server-derived identity rather than
trusting event payload fields.
"""
import sqlite3

from flask import Flask

import websocket_server


def _db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _make_app(tmp_path):
    db_path = tmp_path / "chat.db"
    conn = _db(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            is_banned INTEGER DEFAULT 0
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            video_id TEXT UNIQUE NOT NULL,
            agent_id INTEGER NOT NULL,
            is_removed INTEGER DEFAULT 0
        );
        CREATE TABLE chat_messages (
            id TEXT PRIMARY KEY,
            video_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            is_super INTEGER NOT NULL DEFAULT 0,
            tip_amount REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );
        CREATE TABLE chat_bans (
            id TEXT PRIMARY KEY,
            video_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            banned_by TEXT NOT NULL,
            reason TEXT,
            expires_at REAL,
            created_at REAL NOT NULL
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (id, agent_name, api_key) VALUES (?, ?, ?)",
        [(1, "alice", "alice-key"), (2, "bob", "bob-key")],
    )
    conn.execute(
        "INSERT INTO videos (id, video_id, agent_id) VALUES (1, 'video-a', 1)"
    )
    conn.commit()
    conn.close()

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.testing = True
    websocket_server._socket_identities.clear()
    websocket_server._last_message_time.clear()
    websocket_server.init_socketio(
        app,
        db_path=str(db_path),
        admin_key="admin-secret",
    )
    return app, db_path


def test_unauthenticated_socket_is_rejected(tmp_path):
    app, _ = _make_app(tmp_path)
    client = websocket_server.socketio.test_client(app)
    assert not client.is_connected()


def test_api_key_identity_overrides_spoofed_payload_identity(tmp_path):
    app, db_path = _make_app(tmp_path)
    client = websocket_server.socketio.test_client(
        app,
        headers={"X-API-Key": "alice-key"},
    )
    assert client.is_connected()

    client.emit(
        "chat_message",
        {
            "video_id": "video-a",
            "user_id": 2,
            "username": "bob",
            "message": "hello",
        },
    )

    conn = _db(db_path)
    row = conn.execute(
        "SELECT user_id, username, message FROM chat_messages"
    ).fetchone()
    conn.close()
    assert dict(row) == {
        "user_id": 1,
        "username": "alice",
        "message": "hello",
    }


def test_non_owner_cannot_moderate(tmp_path):
    app, db_path = _make_app(tmp_path)
    client = websocket_server.socketio.test_client(
        app,
        headers={"X-API-Key": "bob-key"},
    )
    client.emit(
        "mod_action",
        {
            "action": "ban",
            "video_id": "video-a",
            "target_user_id": 1,
            "mod_name": "alice",
        },
    )

    conn = _db(db_path)
    count = conn.execute("SELECT COUNT(*) FROM chat_bans").fetchone()[0]
    conn.close()
    assert count == 0
    assert any(
        packet["name"] == "error"
        and packet["args"][0]["message"] == "Moderator authorization required"
        for packet in client.get_received()
    )


def test_video_owner_moderation_records_authenticated_actor(tmp_path):
    app, db_path = _make_app(tmp_path)
    client = websocket_server.socketio.test_client(
        app,
        headers={"X-API-Key": "alice-key"},
    )
    client.emit(
        "mod_action",
        {
            "action": "ban",
            "video_id": "video-a",
            "target_user_id": 2,
            "mod_name": "spoofed-admin",
            "reason": "spam",
        },
    )

    conn = _db(db_path)
    row = conn.execute(
        "SELECT user_id, banned_by, reason FROM chat_bans"
    ).fetchone()
    conn.close()
    assert dict(row) == {
        "user_id": 2,
        "banned_by": "alice",
        "reason": "spam",
    }


def test_admin_credential_elevates_authenticated_non_owner(tmp_path):
    app, db_path = _make_app(tmp_path)
    client = websocket_server.socketio.test_client(
        app,
        headers={
            "X-API-Key": "bob-key",
            "X-Admin-Key": "admin-secret",
        },
    )
    client.emit(
        "mod_action",
        {
            "action": "ban",
            "video_id": "video-a",
            "target_user_id": 1,
        },
    )

    conn = _db(db_path)
    row = conn.execute(
        "SELECT user_id, banned_by FROM chat_bans"
    ).fetchone()
    conn.close()
    assert dict(row) == {"user_id": 1, "banned_by": "bob"}


def test_browser_session_auth_binds_existing_agent(tmp_path):
    app, _ = _make_app(tmp_path)
    with app.test_client() as flask_client:
        with flask_client.session_transaction() as session:
            session["user_id"] = 1
        client = websocket_server.socketio.test_client(
            app,
            flask_test_client=flask_client,
        )
        assert client.is_connected()
        received = client.get_received()
        assert any(
            packet["name"] == "authenticated"
            and packet["args"][0]["username"] == "alice"
            for packet in received
        )
