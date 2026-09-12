# SPDX-License-Identifier: MIT
"""
Tests for Issue #2154 and Issue #2157:
Ensure live chat routes (REST & WebSocket) reject nonexistent or removed videos
with 404 / error and do not create orphan chat messages, bans, or settings rows.
"""

import importlib
import sqlite3
import sys
import types
import pytest
from flask import Flask, g
import chat_handlers


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


@pytest.fixture
def chat_app_with_videos(tmp_path):
    db_path = tmp_path / "chat_with_videos.db"

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["DATABASE"] = str(db_path)
    app.config["CHAT_DB_PATH"] = str(db_path)
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
        # Create videos table
        db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                is_removed INTEGER DEFAULT 0
            )
        """)
        # Insert one active video and one removed video
        db.execute("INSERT INTO videos (video_id, title, is_removed) VALUES ('valid-video', 'Valid Video', 0)")
        db.execute("INSERT INTO videos (video_id, title, is_removed) VALUES ('removed-video', 'Removed Video', 1)")
        db.commit()

    client = app.test_client()
    client.db_path = db_path
    client.app = app
    return client


def test_history_404_for_nonexistent_video(chat_app_with_videos):
    resp = chat_app_with_videos.get("/api/chat/ghost-video/history")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Video not found"}


def test_history_404_for_removed_video(chat_app_with_videos):
    resp = chat_app_with_videos.get("/api/chat/removed-video/history")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Video not found"}


def test_history_200_for_valid_video(chat_app_with_videos):
    resp = chat_app_with_videos.get("/api/chat/valid-video/history")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_send_404_for_nonexistent_video_no_orphan(chat_app_with_videos):
    resp = chat_app_with_videos.post("/api/chat/ghost-video/send", json={"message": "hello"})
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Video not found"}
    with sqlite3.connect(chat_app_with_videos.db_path) as db:
        count = db.execute("SELECT COUNT(*) FROM chat_messages WHERE video_id = 'ghost-video'").fetchone()[0]
        assert count == 0


def test_send_200_for_valid_video(chat_app_with_videos):
    resp = chat_app_with_videos.post("/api/chat/valid-video/send", json={"message": "hello valid"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "sent"
    with sqlite3.connect(chat_app_with_videos.db_path) as db:
        count = db.execute("SELECT COUNT(*) FROM chat_messages WHERE video_id = 'valid-video'").fetchone()[0]
        assert count == 1


def test_ban_404_for_nonexistent_video_no_orphan(chat_app_with_videos):
    with chat_app_with_videos.session_transaction() as sess:
        sess["is_mod"] = True
        sess["username"] = "mod"
    resp = chat_app_with_videos.post("/api/chat/ghost-video/ban", json={"user_id": "spammer"})
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Video not found"}
    with sqlite3.connect(chat_app_with_videos.db_path) as db:
        count = db.execute("SELECT COUNT(*) FROM chat_bans WHERE video_id = 'ghost-video'").fetchone()[0]
        assert count == 0


def test_settings_404_for_nonexistent_video(chat_app_with_videos):
    with chat_app_with_videos.session_transaction() as sess:
        sess["is_mod"] = True
        sess["username"] = "mod"
    resp = chat_app_with_videos.get("/api/chat/ghost-video/settings")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Video not found"}


def test_websocket_chat_rejects_nonexistent_video(chat_app_with_videos, monkeypatch):
    ws_module, events = _load_websocket_server(monkeypatch)

    with chat_app_with_videos.app.app_context():
        ws_module.on_chat_message({
            "video_id": "ghost-video",
            "message": "hello",
            "username": "tester"
        })

    assert len(events) == 1
    args, _ = events[0]
    assert args[0] == "error"
    assert args[1] == {"message": "Video not found"}
    with sqlite3.connect(chat_app_with_videos.db_path) as db:
        count = db.execute("SELECT COUNT(*) FROM chat_messages WHERE video_id = 'ghost-video'").fetchone()[0]
        assert count == 0
