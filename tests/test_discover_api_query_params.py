# SPDX-License-Identifier: MIT

import sqlite3

import pytest
from flask import Flask, g

from search_blueprint import search_bp


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=False)
    app.register_blueprint(search_bp)

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT,
            display_name TEXT,
            avatar_url TEXT,
            bio TEXT,
            api_key TEXT
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            video_id TEXT,
            title TEXT,
            description TEXT,
            thumbnail TEXT,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            tags TEXT DEFAULT '[]',
            category TEXT,
            duration_sec REAL,
            created_at REAL,
            agent_id INTEGER
        );
        CREATE TABLE views (
            id INTEGER PRIMARY KEY,
            video_id TEXT,
            agent_id INTEGER,
            created_at REAL
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY,
            video_id TEXT,
            created_at REAL
        );
        CREATE TABLE subscriptions (
            id INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
        """
    )

    @app.before_request
    def attach_db():
        g.db = db

    with app.test_client() as test_client:
        yield test_client

    db.close()


def test_discover_api_returns_json_400_for_malformed_numeric_params(client):
    endpoints = [
        "/discover/api/search?q=test&limit=abc",
        "/discover/api/tags?limit=abc",
        "/discover/api/trending?limit=abc",
        "/discover/api/agents?limit=abc",
        "/discover/api/tag/test?offset=abc",
        "/discover/api/for-you?limit=abc",
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 400, endpoint
        assert response.is_json, endpoint
        assert response.get_json()["error"] == "Invalid numeric query parameter"


def test_discover_api_clamps_negative_pagination_params(client):
    response = client.get("/discover/api/search?q=test&limit=-1&offset=-5")

    assert response.status_code == 200
    data = response.get_json()
    assert data["limit"] == 1
    assert data["offset"] == 0
