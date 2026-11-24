# SPDX-License-Identifier: MIT
"""Regression tests for /social/api/threads/<video_id> visibility and 404 handling."""

import sqlite3
import time

import pytest
from flask import Flask, g

import interactions_blueprint


@pytest.fixture()
def threads_client(tmp_path):
    db_path = tmp_path / "threads_visibility.db"
    db = sqlite3.connect(db_path)
    db.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT NOT NULL,
            display_name TEXT,
            avatar_url TEXT,
            is_banned INTEGER DEFAULT 0
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            video_id TEXT NOT NULL UNIQUE,
            agent_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            is_removed INTEGER DEFAULT 0
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY,
            video_id TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            parent_id INTEGER,
            content TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            is_removed INTEGER DEFAULT 0,
            created_at REAL NOT NULL
        );
        """
    )
    now = time.time()
    db.executemany(
        "INSERT INTO agents VALUES (?, ?, ?, '', ?)",
        [
            (1, "visible_owner", "Visible Owner", 0),
            (2, "visible_commenter", "Visible Commenter", 0),
            (3, "banned_author", "Banned Author", 1),
        ],
    )
    db.executemany(
        "INSERT INTO videos VALUES (?, ?, ?, ?, ?)",
        [
            (1, "pub-vid", 1, "Public Video", 0),
            (2, "rem-vid", 1, "Removed Video", 1),
            (3, "ban-vid", 3, "Banned Owner Video", 0),
        ],
    )
    parent_visible = db.execute(
        "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
        ("pub-vid", 2, "Visible root", now - 3),
    ).lastrowid
    parent_banned = db.execute(
        "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
        ("pub-vid", 3, "Banned root", now - 2),
    ).lastrowid
    db.execute(
        "INSERT INTO comments (video_id, agent_id, parent_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
        ("pub-vid", 2, parent_banned, "Visible reply to banned", now - 1),
    )
    db.execute(
        "INSERT INTO comments (video_id, agent_id, parent_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
        ("pub-vid", 3, parent_visible, "Banned reply", now),
    )
    db.execute(
        "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
        ("rem-vid", 2, "Leaked on removed video", now),
    )
    db.execute(
        "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
        ("ban-vid", 2, "Leaked on banned owner video", now),
    )
    db.commit()
    db.close()

    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.before_request
    def open_db():
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row

    @app.teardown_request
    def close_db(_error):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    app.register_blueprint(interactions_blueprint.interactions_bp)
    return app.test_client()


def test_threads_returns_404_for_missing_removed_or_banned_owner_video(threads_client):
    for vid in ("nonexistent-video", "rem-vid", "ban-vid"):
        resp = threads_client.get(f"/social/api/threads/{vid}")
        assert resp.status_code == 404
        assert resp.get_json() == {"error": "Video not found"}


def test_threads_hides_banned_commenters_and_keeps_total_consistent(threads_client):
    resp = threads_client.get("/social/api/threads/pub-vid")
    assert resp.status_code == 200
    body = resp.get_json()
    contents = [item["content"] for item in body["threads"]]
    assert contents == ["Visible root", "Visible reply to banned"]
    assert body["total_comments"] == 2
    assert all(item["agent"]["name"] != "banned_author" for item in body["threads"])
