from flask import Flask

import interactions_blueprint
from interactions_blueprint import interactions_bp


class FakeResult:
    def fetchall(self):
        return []


class FakeDB:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return FakeResult()


def _make_client(monkeypatch):
    fake_db = FakeDB()
    monkeypatch.setattr(interactions_blueprint, "get_db", lambda: fake_db)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(interactions_bp)
    return app.test_client(), fake_db


def test_social_feed_rejects_malformed_limit(monkeypatch):
    client, fake_db = _make_client(monkeypatch)

    resp = client.get("/social/api/feed?limit=abc")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "limit must be an integer"}
    assert fake_db.calls == []


def test_social_feed_rejects_malformed_since(monkeypatch):
    client, fake_db = _make_client(monkeypatch)

    resp = client.get("/social/api/feed?since=abc")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "since must be a number"}
    assert fake_db.calls == []


def test_social_feed_clamps_limit_and_applies_since(monkeypatch):
    client, fake_db = _make_client(monkeypatch)

    resp = client.get("/social/api/feed?limit=250&since=100.5")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["activities"] == []
    assert body["count"] == 0
    assert len(fake_db.calls) == 4
    assert all(params == [100.5, 100] for _, params in fake_db.calls)
