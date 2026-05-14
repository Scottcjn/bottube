# SPDX-License-Identifier: MIT

import sqlite3
import sys
import types

import pytest
from flask import Flask, g

from agent_discovery import discovery_bp


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=False)
    app.register_blueprint(discovery_bp)

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT,
            display_name TEXT,
            bio TEXT,
            is_human INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            created_at REAL
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            agent_id INTEGER,
            views INTEGER DEFAULT 0,
            is_removed INTEGER DEFAULT 0,
            created_at REAL
        );
        INSERT INTO agents (id, agent_name, display_name, bio, created_at)
        VALUES (1, 'agent_one', 'Agent One', 'testing', 1770000000);
        INSERT INTO videos (id, agent_id, views, created_at)
        VALUES (1, 1, 7, 1770000100);
        """
    )

    @app.before_request
    def attach_db():
        g.db = db

    fake_server = types.ModuleType("bottube_server")
    fake_server.get_db = lambda: g.db
    monkeypatch.setitem(sys.modules, "bottube_server", fake_server)

    with app.test_client() as test_client:
        yield test_client

    db.close()


def test_api_agents_returns_json_400_for_malformed_pagination(client):
    for endpoint in ["/api/agents?limit=abc", "/api/agents?page=abc"]:
        response = client.get(endpoint)

        assert response.status_code == 400, endpoint
        assert response.is_json, endpoint
        assert response.get_json()["error"] == "Invalid numeric query parameter"


def test_api_agents_valid_limit_still_returns_json(client):
    response = client.get("/api/agents?limit=1")

    assert response.status_code == 200
    data = response.get_json()
    assert data["limit"] == 1
    assert data["agents"][0]["agent_name"] == "agent_one"
