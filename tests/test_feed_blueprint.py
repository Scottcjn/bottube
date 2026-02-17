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


def test_to_rfc2822_supports_epoch_string():
    out = feed._to_rfc2822("1700000000")
    assert "+0000" in out
    assert "2023" in out


def test_rss_route_uses_video_created_at_and_content_type(monkeypatch):
    payload = [
        {
            "id": "vid123",
            "title": "Hello",
            "description": "desc",
            "agent_name": "agent",
            "category": "news",
            "created_at": "2026-02-16T12:34:56Z",
        }
    ]

    monkeypatch.setattr(feed.requests, "get", lambda *args, **kwargs: _Resp(payload))

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
    # should still render channel with no items, and clamp limit not crash
    assert "<channel>" in body
    assert "<item>" not in body
