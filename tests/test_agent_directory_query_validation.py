# SPDX-License-Identifier: MIT
import sys
import types

import pytest
from flask import Flask


class FakeResult:
    def __init__(self, one=None, rows=None):
        self.one = one
        self.rows = rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class FakeDB:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "COUNT(*)" in sql:
            return FakeResult(one=(0,))
        return FakeResult(rows=[])


@pytest.fixture
def agent_directory_client(monkeypatch):
    fake_db = FakeDB()
    monkeypatch.setitem(
        sys.modules,
        "bottube_server",
        types.SimpleNamespace(get_db=lambda: fake_db),
    )

    from agent_discovery import discovery_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(discovery_bp)
    return app.test_client(), fake_db


def test_agent_directory_rejects_malformed_limit(agent_directory_client):
    client, fake_db = agent_directory_client

    resp = client.get("/api/agents?limit=abc")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "limit must be an integer"}
    assert fake_db.calls == []


def test_agent_directory_rejects_malformed_page(agent_directory_client):
    client, fake_db = agent_directory_client

    resp = client.get("/api/agents?page=abc")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "page must be an integer"}
    assert fake_db.calls == []


def test_agent_directory_clamps_valid_numeric_bounds(agent_directory_client):
    client, fake_db = agent_directory_client

    resp = client.get("/api/agents?page=0&limit=250")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["page"] == 1
    assert body["limit"] == 100
    assert body["total"] == 0
    assert len(fake_db.calls) == 2


@pytest.mark.parametrize("sort", ["newest", "popular", "active"])
def test_agent_directory_accepts_valid_sort(agent_directory_client, sort):
    client, fake_db = agent_directory_client

    resp = client.get(f"/api/agents?sort={sort}")

    assert resp.status_code == 200
    assert resp.get_json()["sort"] == sort
    assert len(fake_db.calls) == 2


def test_agent_directory_rejects_invalid_sort(agent_directory_client):
    client, fake_db = agent_directory_client

    resp = client.get("/api/agents?sort=trending")

    assert resp.status_code == 400
    assert resp.get_json() == {
        "error": "sort must be one of: newest, popular, active"
    }
    assert fake_db.calls == []


@pytest.mark.parametrize("agent_type", ["agent", "human", "all"])
def test_agent_directory_accepts_valid_type(agent_directory_client, agent_type):
    client, fake_db = agent_directory_client

    resp = client.get(f"/api/agents?type={agent_type}")

    assert resp.status_code == 200
    assert len(fake_db.calls) == 2


def test_agent_directory_rejects_invalid_type(agent_directory_client):
    client, fake_db = agent_directory_client

    resp = client.get("/api/agents?type=robot")

    assert resp.status_code == 400
    assert resp.get_json() == {
        "error": "type must be one of: agent, human, all"
    }
    assert fake_db.calls == []


def test_agent_directory_empty_sort_uses_default(agent_directory_client):
    client, fake_db = agent_directory_client

    resp = client.get("/api/agents?sort=")

    assert resp.status_code == 200
    assert resp.get_json()["sort"] == "popular"
    assert len(fake_db.calls) == 2
