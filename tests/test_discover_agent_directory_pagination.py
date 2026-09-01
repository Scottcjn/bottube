# SPDX-License-Identifier: MIT
import sqlite3
import time

import pytest
from flask import Flask

import search_blueprint
from search_blueprint import search_bp


@pytest.fixture()
def agent_directory_client(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT,
            display_name TEXT,
            avatar_url TEXT,
            bio TEXT
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            video_id TEXT,
            agent_id INTEGER,
            created_at REAL
        );
        CREATE TABLE subscriptions (
            follower_id INTEGER,
            following_id INTEGER
        );
        """
    )
    now = time.time()
    for agent_id, name, video_count in (
        (1, "three_videos", 3),
        (2, "two_videos", 2),
        (3, "one_video", 1),
    ):
        conn.execute(
            "INSERT INTO agents VALUES (?, ?, ?, '', '')",
            (agent_id, name, name.replace("_", " ").title()),
        )
        for index in range(video_count):
            conn.execute(
                "INSERT INTO videos VALUES (NULL, ?, ?, ?)",
                (f"{name}-{index}", agent_id, now - index),
            )
    conn.commit()

    monkeypatch.setattr(search_blueprint, "get_db", lambda: conn)
    app = Flask(__name__)
    app.register_blueprint(search_bp)
    app.config["TESTING"] = True

    yield app.test_client()

    conn.close()


def test_agent_directory_applies_documented_offset(agent_directory_client):
    response = agent_directory_client.get(
        "/discover/api/agents?sort=videos&limit=1&offset=1"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert [agent["name"] for agent in payload["agents"]] == ["two_videos"]


@pytest.mark.parametrize("offset", ["bad", "-1"])
def test_agent_directory_rejects_invalid_offset(
    agent_directory_client, offset
):
    response = agent_directory_client.get(
        f"/discover/api/agents?offset={offset}"
    )

    assert response.status_code == 400
    assert "offset" in response.get_json()["error"]
