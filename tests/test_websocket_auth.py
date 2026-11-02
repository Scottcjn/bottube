"""Security regressions for the dormant Socket.IO chat layer.

These cases pin the authorization contract required before init_socketio() is
wired into production. They exercise server-derived identity rather than
trusting event payload fields.
"""
from contextlib import closing
from types import SimpleNamespace
import json
import sqlite3

from flask import Flask
import pytest

import websocket_server


def _db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _make_app(tmp_path, allowed_origins=None):
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
    app.config["CHAT_ALLOWED_ORIGINS"] = allowed_origins
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


@pytest.mark.parametrize("allowed_origins", [None, "", []])
def test_polling_rejects_cross_origin_session_by_default(tmp_path, allowed_origins):
    app, db_path = _make_app(tmp_path, allowed_origins)
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
        response = client.get(
            "/socket.io/?EIO=4&transport=polling",
            headers={"Origin": "https://untrusted.example"},
        )
    assert response.status_code == 400
    with closing(_db(db_path)) as db:
        count = db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        assert count == 0


def test_polling_rejects_origin_outside_configured_allowlist(tmp_path):
    app, _ = _make_app(tmp_path, ["https://trusted.example"])
    response = app.test_client().get(
        "/socket.io/?EIO=4&transport=polling",
        headers={"Origin": "https://untrusted.example"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "allowed_origins, origin, use_api_key",
    [
        (None, "http://localhost", False),
        (None, None, True),
        (["https://trusted.example"], "https://trusted.example", False),
        ("https://trusted.example", "https://trusted.example", False),
    ],
)
def test_allowed_polling_client_authenticates_and_writes(
    tmp_path, allowed_origins, origin, use_api_key
):
    app, db_path = _make_app(tmp_path, allowed_origins)
    headers = {"Origin": origin} if origin else {}
    if use_api_key:
        headers["X-API-Key"] = "alice-key"
    with app.test_client() as client:
        if not use_api_key:
            with client.session_transaction() as session:
                session["user_id"] = 1
        # Exercise Engine.IO's HTTP origin check, which socketio.test_client
        # bypasses when it dispatches directly to Socket.IO handlers.
        path = "/socket.io/?EIO=4&transport=polling"
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        sid = json.loads(response.get_data(as_text=True)[1:])["sid"]
        path += "&sid=" + sid
        try:
            assert client.post(path, data="40", headers=headers).status_code == 200
            response = client.get(path, headers=headers)
            packets = response.get_data(as_text=True).split("\x1e")
            assert any(
                packet.startswith('42["authenticated",') for packet in packets
            )
            message = [
                "chat_message", {"video_id": "video-a", "message": "hello"}
            ]
            assert client.post(
                path, data="421" + json.dumps(message), headers=headers
            ).status_code == 200
            response = client.get(path, headers=headers)
            packets = response.get_data(as_text=True).split("\x1e")
            assert "431[]" in packets  # Handler completed before reading SQLite.
        finally:
            client.post(path, data="41", headers=headers)
    with closing(_db(db_path)) as db:
        row = db.execute(
            "SELECT user_id, username, message FROM chat_messages"
        ).fetchone()
        assert dict(row) == {"user_id": 1, "username": "alice", "message": "hello"}


def test_room_alias_cannot_bypass_existing_ban(tmp_path):
    app, db_path = _make_app(tmp_path)
    owner = websocket_server.socketio.test_client(
        app, headers={"X-API-Key": "alice-key"}
    )
    banned = websocket_server.socketio.test_client(
        app, headers={"X-API-Key": "bob-key"}
    )
    owner.emit(
        "mod_action",
        {"action": "ban", "video_id": "video-a", "target_user_id": 2},
    )
    banned.emit(
        "chat_message", {"video_id": " video-a ", "message": "blocked user"}
    )
    with closing(_db(db_path)) as db:
        assert db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0
    assert any(
        packet["name"] == "error"
        and packet["args"][0]["message"] == "You are banned from this chat."
        for packet in banned.get_received()
    )


def test_room_alias_joins_messages_and_leaves_canonical_room(tmp_path):
    app, db_path = _make_app(tmp_path)
    observer = websocket_server.socketio.test_client(
        app, headers={"X-API-Key": "alice-key"}
    )
    sender = websocket_server.socketio.test_client(
        app, headers={"X-API-Key": "bob-key"}
    )
    observer.emit("join", {"video_id": "video-a"})
    observer.get_received()
    sender.get_received()
    padded_id = " \tvideo-a\n "
    sender.emit("join", {"video_id": padded_id})
    assert any(
        p["name"] == "system" and p["args"][0]["message"] == "bob joined the chat"
        for p in observer.get_received()
    )
    sender.get_received()
    sender.emit("chat_message", {"video_id": padded_id, "message": "hello"})
    for client in (observer, sender):
        assert any(
            p["name"] == "new_message" and p["args"][0]["message"] == "hello"
            for p in client.get_received()
        )
    with closing(_db(db_path)) as db:
        row = db.execute("SELECT video_id, user_id FROM chat_messages").fetchone()
        assert dict(row) == {"video_id": "video-a", "user_id": 2}

    sender.emit("leave", {"video_id": padded_id})
    assert any(
        p["name"] == "system" and p["args"][0]["message"] == "bob left the chat"
        for p in observer.get_received()
    )
    observer.emit("chat_message", {"video_id": "video-a", "message": "after leave"})
    assert not any(p["name"] == "new_message" for p in sender.get_received())


def test_room_alias_owner_moderation_keeps_canonical_scope(tmp_path):
    app, db_path = _make_app(tmp_path)
    owner = websocket_server.socketio.test_client(
        app, headers={"X-API-Key": "alice-key"}
    )
    owner.emit(
        "mod_action",
        {"action": "ban", "video_id": " video-a ", "target_user_id": 2},
    )
    with closing(_db(db_path)) as db:
        row = db.execute("SELECT video_id, user_id, banned_by FROM chat_bans").fetchone()
        assert row is not None
        assert dict(row) == {
            "video_id": "video-a", "user_id": 2, "banned_by": "alice"
        }


def test_room_alias_shares_message_budget(tmp_path, monkeypatch):
    app, db_path = _make_app(tmp_path)
    monkeypatch.setattr(websocket_server, "time", SimpleNamespace(time=lambda: 1000.0))
    sender = websocket_server.socketio.test_client(
        app, headers={"X-API-Key": "bob-key"}
    )
    sender.emit("chat_message", {"video_id": " video-a ", "message": "first"})
    sender.emit("chat_message", {"video_id": "video-a", "message": "second"})
    with closing(_db(db_path)) as db:
        rows = db.execute("SELECT video_id, message FROM chat_messages").fetchall()
        assert [dict(row) for row in rows] == [
            {"video_id": "video-a", "message": "first"}
        ]
    assert any(
        packet["name"] == "error"
        and packet["args"][0]["message"] == "Slow down! Wait 2 seconds between messages."
        for packet in sender.get_received()
    )
