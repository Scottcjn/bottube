# SPDX-License-Identifier: MIT
import sqlite3
import time
from pathlib import Path

import pytest
from flask import Flask, g

import search_blueprint
from search_blueprint import search_bp


@pytest.fixture()
def signed_in_discover_client(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT,
            display_name TEXT,
            api_key TEXT
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
        "INSERT INTO agents VALUES (1, 'signed_in_viewer', 'Signed In Viewer', 'viewer-key')"
    )
    conn.execute(
        "INSERT INTO agents VALUES (2, 'creator', 'Creator', 'creator-key')"
    )
    conn.execute(
        """INSERT INTO videos VALUES
           (1, 'already-viewed', 'Already viewed', '', '', 10, 1,
            '["python"]', 'education', 10, ?, 2)""",
        (now - 100,),
    )
    conn.execute(
        """INSERT INTO videos VALUES
           (2, 'session-match', 'Session match', '', '', 4, 1,
            '["python"]', 'education', 10, ?, 2)""",
        (now,),
    )
    conn.execute(
        "INSERT INTO views VALUES ('already-viewed', 1, ?)",
        (now - 50,),
    )
    conn.commit()

    monkeypatch.setattr(search_blueprint, "get_db", lambda: conn)

    app = Flask(__name__)

    @app.before_request
    def load_signed_in_user():
        g.user = conn.execute("SELECT * FROM agents WHERE id = 1").fetchone()

    app.register_blueprint(search_bp)
    app.config["TESTING"] = True

    yield app.test_client()

    conn.close()


def test_for_you_uses_signed_in_web_session_without_api_key(
    signed_in_discover_client,
):
    response = signed_in_discover_client.get("/discover/api/for-you")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["personalized"] is True
    assert payload["based_on"]["categories"] == ["education"]
    assert [video["id"] for video in payload["videos"]] == ["session-match"]


def test_discover_ui_relies_on_session_credentials_not_local_storage_identity():
    template = Path("bottube_templates/discover.html").read_text(encoding="utf-8")

    assert "localStorage.getItem('agent_id')" not in template
    assert "fetch('/discover/api/for-you', { credentials: 'same-origin' })" in template
