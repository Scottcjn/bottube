# SPDX-License-Identifier: MIT
"""Regression tests for discover gallery thumbnail URLs."""

import sqlite3
import time
from pathlib import Path

import pytest
from flask import Flask

import search_blueprint
from search_blueprint import search_bp


@pytest.fixture()
def discover_thumbnail_client(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT,
            display_name TEXT
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
            agent_id INTEGER
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
        """
    )
    now = time.time()
    conn.execute(
        "INSERT INTO agents (id, agent_name, display_name) VALUES (1, 'thumbbot', 'Thumb Bot')"
    )
    conn.execute(
        """INSERT INTO videos
           (id, video_id, title, description, thumbnail, views, likes, tags, category, duration_sec, created_at, agent_id)
           VALUES (1, 'thumb-video', 'Thumbnail demo', 'Demo video', 'sample thumb.jpg',
                   9, 3, '["python"]', 'education', 12.5, ?, 1)""",
        (now,),
    )
    conn.execute(
        "INSERT INTO views (video_id, agent_id, created_at) VALUES ('thumb-video', 1, ?)",
        (now,),
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
        "/discover/api/search?q=Thumbnail",
        "/discover/api/tag/python",
        "/discover/api/trending",
        "/discover/api/for-you",
    ],
)
def test_discover_video_apis_expose_loadable_thumbnail_url(discover_thumbnail_client, path):
    response = discover_thumbnail_client.get(path)

    assert response.status_code == 200
    video = response.get_json()["videos"][0]
    assert video["thumbnail"] == "sample thumb.jpg"
    assert video["thumbnail_url"] == "/thumbnails/sample%20thumb.jpg"


def test_discover_template_prefers_thumbnail_url():
    template = Path("bottube_templates/discover.html").read_text(encoding="utf-8")

    assert "video.thumbnail_url" in template
    assert "/thumbnails/${encodeURIComponent(video.thumbnail)}" in template
