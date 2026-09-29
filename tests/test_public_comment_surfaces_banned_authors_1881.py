# SPDX-License-Identifier: MIT
import sqlite3
import time
from flask import Flask
import pytest

import bottube_server
import interactions_blueprint
import search_blueprint


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_comments_banned.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(interactions_blueprint.interactions_bp)
    app.register_blueprint(search_blueprint.search_bp)

    @app.route("/api/videos/<video_id>/comments")
    def get_video_comments_route(video_id):
        return bottube_server.get_comments(video_id)

    def get_test_db():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(bottube_server, "get_db", get_test_db)
    monkeypatch.setattr(interactions_blueprint, "get_db", get_test_db)
    monkeypatch.setattr(search_blueprint, "get_db", get_test_db)

    with app.app_context():
        conn = get_test_db()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT UNIQUE,
                display_name TEXT,
                avatar_url TEXT,
                api_key TEXT,
                is_banned INTEGER DEFAULT 0,
                is_human INTEGER DEFAULT 0,
                created_at REAL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE,
                agent_id INTEGER,
                title TEXT,
                description TEXT,
                category TEXT,
                duration_sec INTEGER DEFAULT 60,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                is_removed INTEGER DEFAULT 0,
                created_at REAL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                agent_id INTEGER,
                content TEXT,
                comment_type TEXT DEFAULT 'comment',
                parent_id INTEGER DEFAULT NULL,
                likes INTEGER DEFAULT 0,
                dislikes INTEGER DEFAULT 0,
                created_at REAL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                agent_id INTEGER,
                vote INTEGER,
                created_at REAL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                agent_id INTEGER,
                created_at REAL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                follower_id INTEGER,
                following_id INTEGER,
                created_at REAL
            )
        """)

        now = time.time()
        # Insert owner
        conn.execute("INSERT OR REPLACE INTO agents (id, agent_name, display_name, is_banned) VALUES (1, 'owner_agent', 'Owner Agent', 0)")
        # Insert good commenter
        conn.execute("INSERT OR REPLACE INTO agents (id, agent_name, display_name, is_banned) VALUES (2, 'good_commenter', 'Good Commenter', 0)")
        # Insert banned commenter
        conn.execute("INSERT OR REPLACE INTO agents (id, agent_name, display_name, is_banned) VALUES (3, 'banned_commenter', 'Banned Commenter', 1)")

        # Insert video
        conn.execute("INSERT OR REPLACE INTO videos (id, video_id, agent_id, title, is_removed, created_at) VALUES (1, 'v100', 1, 'Test Video', 0, ?)", (now,))

        # Insert comments
        conn.execute("INSERT OR REPLACE INTO comments (id, video_id, agent_id, content, created_at) VALUES (10, 'v100', 2, 'Good comment', ?)", (now,))
        conn.execute("INSERT OR REPLACE INTO comments (id, video_id, agent_id, content, created_at) VALUES (11, 'v100', 3, 'Banned comment', ?)", (now,))

        conn.commit()
        conn.close()

    with app.test_client() as test_client:
        yield test_client


def test_video_comments_endpoint_hides_banned_authors(client):
    res = client.get("/api/videos/v100/comments")
    assert res.status_code == 200
    data = res.get_json()
    assert "comments" in data
    agent_names = [c["agent_name"] for c in data["comments"]]
    assert "good_commenter" in agent_names
    assert "banned_commenter" not in agent_names


def test_api_comment_threads_hides_banned_authors(client):
    res = client.get("/social/api/threads/v100")
    assert res.status_code == 200
    data = res.get_json()
    assert "threads" in data
    assert len(data["threads"]) == 1
    assert data["threads"][0]["content"] == "Good comment"
