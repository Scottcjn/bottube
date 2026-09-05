"""Regression coverage for public video IDs in interaction queries."""

import sqlite3
import time

import pytest
from flask import Flask, g

import interactions_blueprint


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "interactions.db"
    db = sqlite3.connect(db_path)
    db.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT NOT NULL,
            display_name TEXT,
            avatar_url TEXT,
            created_at REAL
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            video_id TEXT NOT NULL UNIQUE,
            agent_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            thumbnail TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY,
            video_id TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            parent_id INTEGER,
            content TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            created_at REAL NOT NULL
        );
        CREATE TABLE votes (
            agent_id INTEGER NOT NULL,
            video_id TEXT NOT NULL,
            vote INTEGER NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE TABLE tips (
            id INTEGER PRIMARY KEY,
            from_agent_id INTEGER NOT NULL,
            to_agent_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT,
            message TEXT,
            created_at REAL NOT NULL
        );
        """
    )
    now = time.time()
    db.executemany(
        "INSERT INTO agents VALUES (?, ?, ?, ?, ?)",
        [
            (1, "alice", "Alice", "", now),
            (2, "bob", "Bob", "", now),
        ],
    )
    # Deliberately make the internal id different from the public video_id.
    db.execute(
        "INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?)",
        (41, "public-video-41", 1, "Public video", "thumb.jpg", now),
    )
    parent_id = db.execute(
        "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
        ("public-video-41", 1, "Parent", now - 2),
    ).lastrowid
    db.execute(
        "INSERT INTO comments (video_id, agent_id, parent_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
        ("public-video-41", 2, parent_id, "Reply", now - 1),
    )
    # Three additional comments make Alice a collaboration partner for Bob.
    db.executemany(
        "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
        [("public-video-41", 2, f"Comment {index}", now + index) for index in range(3)],
    )
    db.execute(
        "INSERT INTO votes VALUES (?, ?, ?, ?)",
        (2, "public-video-41", 1, now),
    )
    db.commit()
    db.close()

    app = Flask(__name__)
    app.config.update(TESTING=True)

    @app.before_request
    def open_db():
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row

    @app.teardown_request
    def close_db(_error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    app.register_blueprint(interactions_blueprint.interactions_bp)
    return app.test_client()


def test_activity_feed_includes_comments_and_votes_with_public_video_ids(client):
    response = client.get("/social/api/feed")

    assert response.status_code == 200
    activities = response.get_json()["activities"]
    assert any(item["type"] == "comment" for item in activities)
    assert any(item["type"] == "vote" for item in activities)


def test_collaboration_partners_include_public_video_id_comments(client):
    response = client.get("/social/api/collabs/bob")

    assert response.status_code == 200
    partners = response.get_json()["collaboration_partners"]
    assert any(item["agent"]["name"] == "alice" for item in partners)


def test_conversations_include_replies_on_public_video_ids(client):
    response = client.get("/social/api/conversations/alice/bob")

    assert response.status_code == 200
    data = response.get_json()
    assert data["conversation_count"] == 1
    assert data["dialogue"][0]["video"]["id"] == "public-video-41"
