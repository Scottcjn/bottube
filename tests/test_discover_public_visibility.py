# SPDX-License-Identifier: MIT
import sqlite3
import time

import pytest
from flask import Flask

import search_blueprint
from search_blueprint import search_bp


@pytest.fixture()
def discover_visibility_client(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT,
            display_name TEXT,
            avatar_url TEXT,
            bio TEXT,
            api_key TEXT,
            is_banned INTEGER DEFAULT 0
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            video_id TEXT,
            title TEXT,
            description TEXT,
            thumbnail TEXT,
            views INTEGER,
            likes INTEGER,
            tags TEXT,
            category TEXT,
            duration_sec REAL,
            created_at REAL,
            agent_id INTEGER,
            is_removed INTEGER DEFAULT 0
        );
        CREATE TABLE views (
            video_id TEXT,
            agent_id INTEGER,
            created_at REAL
        );
        CREATE TABLE comments (
            video_id TEXT,
            created_at REAL
        );
        CREATE TABLE subscriptions (
            follower_id INTEGER,
            following_id INTEGER
        );
        """
    )
    now = time.time()
    conn.executemany(
        "INSERT INTO agents VALUES (?, ?, ?, '', '', ?, ?)",
        [
            (1, "visible_creator", "Visible Creator", "visible-key", 0),
            (2, "banned_creator", "Banned Creator", "banned-key", 1),
        ],
    )
    conn.executemany(
        """INSERT INTO videos VALUES
           (NULL, ?, ?, '', '', 10, 2, '["shared"]', 'education',
            10, ?, ?, ?)""",
        [
            ("visible-discover", "Shared visible", now, 1, 0),
            ("removed-discover", "Shared removed", now, 1, 1),
            ("banned-discover", "Shared banned", now, 2, 0),
        ],
    )
    conn.executemany(
        "INSERT INTO views VALUES (?, NULL, ?)",
        [
            ("visible-discover", now),
            ("removed-discover", now),
            ("banned-discover", now),
        ],
    )
    conn.commit()

    monkeypatch.setattr(search_blueprint, "get_db", lambda: conn)
    app = Flask(__name__)
    app.register_blueprint(search_bp)
    app.config["TESTING"] = True

    yield app.test_client()

    conn.close()


@pytest.mark.parametrize(
    "path",
    [
        "/discover/api/search?q=Shared",
        "/discover/api/tag/shared",
        "/discover/api/trending",
        "/discover/api/for-you",
    ],
)
def test_discover_video_catalogs_only_return_public_videos(
    discover_visibility_client, path
):
    response = discover_visibility_client.get(path)

    assert response.status_code == 200
    payload = response.get_json()
    assert [video["id"] for video in payload["videos"]] == [
        "visible-discover"
    ]
    if "total" in payload:
        assert payload["total"] == 1


def test_discover_facets_only_count_public_videos(discover_visibility_client):
    categories = discover_visibility_client.get(
        "/discover/api/categories"
    ).get_json()["categories"]
    education = next(row for row in categories if row["id"] == "education")
    assert education["count"] == 1

    tags = discover_visibility_client.get(
        "/discover/api/tags"
    ).get_json()["tags"]
    assert tags == [{"name": "shared", "count": 1}]


def test_discover_agent_directory_uses_public_video_counts(
    discover_visibility_client,
):
    response = discover_visibility_client.get(
        "/discover/api/agents?sort=videos"
    )

    assert response.status_code == 200
    agents = response.get_json()["agents"]
    assert [agent["name"] for agent in agents] == ["visible_creator"]
    assert agents[0]["videos"] == 1
