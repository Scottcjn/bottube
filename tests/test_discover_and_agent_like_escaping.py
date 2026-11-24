# SPDX-License-Identifier: MIT
"""Regression tests for SQLite LIKE wildcard escaping in discover & agent search."""

import sqlite3
import sys
import types

import pytest
from flask import Flask

import agent_discovery
import search_blueprint


@pytest.fixture()
def populated_search_app(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT NOT NULL,
            display_name TEXT,
            bio TEXT,
            avatar_url TEXT,
            is_human INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            created_at REAL DEFAULT 100.0
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            video_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            thumbnail TEXT,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            tags TEXT,
            category TEXT DEFAULT 'other',
            duration_sec REAL DEFAULT 5.0,
            created_at REAL DEFAULT 100.0,
            agent_id INTEGER NOT NULL,
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
    conn.executemany(
        "INSERT INTO agents (id, agent_name, display_name, bio) VALUES (?, ?, ?, ?)",
        [
            (1, "alpha_bot", "Alpha Bot", "Builds Rust tools"),
            (2, "alphaXbot", "Alpha X", "Another agent"),
            (3, "pct_creator", "100% Real", "Saves 50% time"),
        ],
    )
    conn.executemany(
        """INSERT INTO videos (id, video_id, title, description, tags, agent_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (1, "vid-plain", "Rustchain Intro", "Overview", '["rustchain", "axb"]', 1),
            (2, "vid-pct", "50% Faster Sync", "Benchmark", '["50%", "speed"]', 3),
            (3, "vid-under", "Node_01 Setup", "Config guide", '["node_01", "a_b"]', 2),
        ],
    )
    conn.commit()

    monkeypatch.setattr(search_blueprint, "get_db", lambda: conn)
    monkeypatch.setitem(
        sys.modules,
        "bottube_server",
        types.SimpleNamespace(get_db=lambda: conn),
    )

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(search_blueprint.search_bp)
    app.register_blueprint(agent_discovery.discovery_bp)
    yield app.test_client()
    conn.close()


def test_discover_search_escapes_percent_and_underscore(populated_search_app):
    res_pct = populated_search_app.get("/discover/api/search?q=%25").get_json()
    assert [v["id"] for v in res_pct["videos"]] == ["vid-pct"]
    assert res_pct["total"] == 1

    res_under = populated_search_app.get("/discover/api/search?q=_").get_json()
    assert [v["id"] for v in res_under["videos"]] == ["vid-under"]
    assert res_under["total"] == 1


def test_discover_tag_escapes_wildcards(populated_search_app):
    res_pct = populated_search_app.get("/discover/api/tag/%25").get_json()
    assert res_pct["videos"] == []
    assert res_pct["total"] == 0

    res_literal = populated_search_app.get("/discover/api/tag/a_b").get_json()
    assert [v["id"] for v in res_literal["videos"]] == ["vid-under"]
    assert res_literal["total"] == 1


def test_agent_directory_escapes_percent_and_underscore(populated_search_app):
    res_pct = populated_search_app.get("/api/agents?q=%25").get_json()
    assert [a["agent_name"] for a in res_pct["agents"]] == ["pct_creator"]
    assert res_pct["total"] == 1

    res_under = populated_search_app.get("/api/agents?q=alpha_bot").get_json()
    assert [a["agent_name"] for a in res_under["agents"]] == ["alpha_bot"]
    assert res_under["total"] == 1
