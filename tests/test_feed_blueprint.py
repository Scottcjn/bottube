import pathlib
import sys

from flask import Flask

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import feed_blueprint as feed  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _build_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(feed.feed_bp)
    return app


SAMPLE_VIDEO = {
    "id": "vid123",
    "title": "Hello",
    "description": "desc",
    "agent_name": "agent",
    "category": "news",
    "created_at": "2026-02-16T12:34:56Z",
}


# ── RFC 2822 / ISO 8601 helpers ──────────────────────────────

def test_to_rfc2822_supports_epoch_string():
    out = feed._to_rfc2822("1700000000")
    assert "+0000" in out
    assert "2023" in out


def test_to_iso8601_supports_epoch_string():
    out = feed._to_iso8601("1700000000")
    assert "2023" in out
    assert "T" in out


def test_to_iso8601_supports_iso_input():
    out = feed._to_iso8601("2026-02-16T12:34:56Z")
    assert "2026-02-16" in out


def test_to_iso8601_handles_none():
    out = feed._to_iso8601(None)
    assert "T" in out  # returns current time in ISO format


# ── RSS feed ─────────────────────────────────────────────────

def test_rss_route_uses_video_created_at_and_content_type(monkeypatch):
    monkeypatch.setattr(feed.requests, "get", lambda *args, **kwargs: _Resp([SAMPLE_VIDEO]))

    app = _build_app()
    client = app.test_client()
    resp = client.get("/feed/rss?limit=25")

    assert resp.status_code == 200
    assert "application/rss+xml" in resp.content_type
    body = resp.get_data(as_text=True)
    assert "<pubDate>Mon, 16 Feb 2026 12:34:56 +0000</pubDate>" in body
    assert "<title>Hello</title>" in body


def test_rss_route_handles_non_list_payload(monkeypatch):
    monkeypatch.setattr(feed.requests, "get", lambda *args, **kwargs: _Resp({"error": "oops"}))

    app = _build_app()
    client = app.test_client()
    resp = client.get("/feed/rss?limit=9999")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert '<rss version="2.0"' in body
    assert "<channel>" in body
    assert "<item>" not in body


def test_rss_passes_agent_filter(monkeypatch):
    captured = {}

    def mock_get(*args, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return _Resp([])

    monkeypatch.setattr(feed.requests, "get", mock_get)

    app = _build_app()
    client = app.test_client()
    client.get("/feed/rss?agent=sophia-elya")
    assert captured["params"].get("agent") == "sophia-elya"


def test_rss_passes_category_filter(monkeypatch):
    captured = {}

    def mock_get(*args, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return _Resp([])

    monkeypatch.setattr(feed.requests, "get", mock_get)

    app = _build_app()
    client = app.test_client()
    client.get("/feed/rss?category=music")
    assert captured["params"].get("category") == "music"


# ── Atom feed ────────────────────────────────────────────────

def test_atom_route_returns_valid_atom(monkeypatch):
    monkeypatch.setattr(feed.requests, "get", lambda *args, **kwargs: _Resp([SAMPLE_VIDEO]))

    app = _build_app()
    client = app.test_client()
    resp = client.get("/feed/atom")

    assert resp.status_code == 200
    assert "application/atom+xml" in resp.content_type
    body = resp.get_data(as_text=True)
    assert 'xmlns="http://www.w3.org/2005/Atom"' in body
    assert "<entry>" in body
    assert "<title>Hello</title>" in body
    assert "urn:bottube:video:vid123" in body


def test_atom_route_has_self_link(monkeypatch):
    monkeypatch.setattr(feed.requests, "get", lambda *args, **kwargs: _Resp([]))

    app = _build_app()
    client = app.test_client()
    resp = client.get("/feed/atom?agent=test-bot")

    body = resp.get_data(as_text=True)
    assert 'rel="self"' in body
    assert "agent=test-bot" in body


def test_atom_route_handles_empty(monkeypatch):
    monkeypatch.setattr(feed.requests, "get", lambda *args, **kwargs: _Resp({"error": "oops"}))

    app = _build_app()
    client = app.test_client()
    resp = client.get("/feed/atom")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<feed" in body
    assert "<entry>" not in body


def test_atom_uses_iso8601_timestamps(monkeypatch):
    monkeypatch.setattr(feed.requests, "get", lambda *args, **kwargs: _Resp([SAMPLE_VIDEO]))

    app = _build_app()
    client = app.test_client()
    resp = client.get("/feed/atom")

    body = resp.get_data(as_text=True)
    assert "<updated>2026-02-16" in body
    assert "<published>2026-02-16" in body


def test_atom_media_content(monkeypatch):
    monkeypatch.setattr(feed.requests, "get", lambda *args, **kwargs: _Resp([SAMPLE_VIDEO]))

    app = _build_app()
    client = app.test_client()
    resp = client.get("/feed/atom")

    body = resp.get_data(as_text=True)
    assert 'media:content url="https://bottube.ai/api/videos/vid123/stream"' in body
    assert "media:thumbnail" in body


# ── Shared helpers ───────────────────────────────────────────

def test_normalize_videos_handles_dict_envelope():
    assert len(feed._normalize_videos({"videos": [{"id": 1}]})) == 1


def test_normalize_videos_handles_bare_list():
    assert len(feed._normalize_videos([{"id": 1}, {"id": 2}])) == 2


def test_normalize_videos_handles_garbage():
    assert feed._normalize_videos("not json") == []
    assert feed._normalize_videos(42) == []
    assert feed._normalize_videos(None) == []
