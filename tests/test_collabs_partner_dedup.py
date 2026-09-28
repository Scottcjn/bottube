# SPDX-License-Identifier: MIT
"""Regression coverage for /social/api/collabs/<agent> partner aggregation.

A partner that qualifies through both comments and tips used to appear twice
(one row per source from a UNION ALL) and was double-counted in
``total_partners``. Partners must be merged into one entry per agent.
"""

import sqlite3
import time
import uuid

import pytest
from flask import Flask, g

import interactions_blueprint


SCHEMA = """
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


@pytest.fixture()
def client():
    # Shared-cache in-memory DB so each request's connection sees the fixture data.
    uri = f"file:collabs_dedup_{uuid.uuid4().hex}?mode=memory&cache=shared"
    keeper = sqlite3.connect(uri, uri=True)
    keeper.executescript(SCHEMA)
    now = time.time()
    keeper.executemany(
        "INSERT INTO agents VALUES (?, ?, ?, ?, ?)",
        [
            (1, "alice", "Alice", "", now),
            (2, "bob", "Bob", "", now),
            (3, "carol", "Carol", "", now),
            (4, "dave", "Dave", "", now),
        ],
    )
    keeper.executemany(
        "INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?)",
        [
            (10, "vid-bob", 2, "Bob video", "", now),
            (11, "vid-carol", 3, "Carol video", "", now),
            (12, "vid-dave", 4, "Dave video", "", now),
        ],
    )
    # Alice -> Bob: 4 comments AND 3 confirmed tips (qualifies via both sources).
    keeper.executemany(
        "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
        [("vid-bob", 1, f"c{i}", now + i) for i in range(4)],
    )
    keeper.executemany(
        "INSERT INTO tips (from_agent_id, to_agent_id, amount, status, created_at) VALUES (?, ?, ?, ?, ?)",
        [(1, 2, 1.0, "confirmed", now + i) for i in range(3)],
    )
    # Alice -> Carol: 3 comments only.
    keeper.executemany(
        "INSERT INTO comments (video_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
        [("vid-carol", 1, f"k{i}", now + i) for i in range(3)],
    )
    # Alice -> Dave: 2 confirmed tips only (plus a pending one that must not count).
    keeper.executemany(
        "INSERT INTO tips (from_agent_id, to_agent_id, amount, status, created_at) VALUES (?, ?, ?, ?, ?)",
        [(1, 4, 1.0, "confirmed", now), (1, 4, 1.0, None, now), (1, 4, 1.0, "pending", now)],
    )
    keeper.commit()

    app = Flask(__name__)
    app.config.update(TESTING=True)

    @app.before_request
    def open_db():
        g.db = sqlite3.connect(uri, uri=True)
        g.db.row_factory = sqlite3.Row

    @app.teardown_request
    def close_db(_error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    app.register_blueprint(interactions_blueprint.interactions_bp)
    yield app.test_client()
    keeper.close()


def test_partner_with_comments_and_tips_is_listed_once(client):
    response = client.get("/social/api/collabs/alice")
    assert response.status_code == 200
    data = response.get_json()

    names = [p["agent"]["name"] for p in data["collaboration_partners"]]
    assert sorted(names) == ["bob", "carol", "dave"]
    assert len(names) == len(set(names))
    assert data["total_partners"] == 3


def test_merged_partner_sums_counts_and_keeps_breakdown(client):
    data = client.get("/social/api/collabs/alice").get_json()
    partners = {p["agent"]["name"]: p for p in data["collaboration_partners"]}

    bob = partners["bob"]
    assert bob["interaction_count"] == 7
    assert bob["interaction_breakdown"] == {"comments": 4, "tips": 3}
    assert bob["interaction_type"] == "mixed"
    assert bob["badge"] == "💬 Frequent Interactor"

    assert partners["carol"]["interaction_type"] == "comments"
    assert partners["carol"]["interaction_breakdown"] == {"comments": 3}
    assert partners["dave"]["interaction_type"] == "tips"
    assert partners["dave"]["interaction_count"] == 2

    # Ordered by total interactions, highest first.
    assert data["collaboration_partners"][0]["agent"]["name"] == "bob"
