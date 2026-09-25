import re

from flask import Flask

import news_routes


def test_rss_channel_logo_url_resolves(monkeypatch):
    """Regression: RSS channel image must point to deployed hyphenated asset."""
    monkeypatch.setattr(news_routes, "_get_news_videos", lambda limit=20: [])
    monkeypatch.setattr(news_routes, "_get_weather_videos", lambda limit=10: [])
    app = Flask(__name__)
    app.register_blueprint(news_routes.news_bp)

    resp = app.test_client().get("/news/rss")
    assert resp.status_code == 200
    feed = resp.get_data(as_text=True)

    match = re.search(r"<url>(https://bottube\.ai/static/[^<]+)</url>", feed)
    assert match, "RSS feed missing <image><url>"
    url = match.group(1)
    assert url.endswith("bottube-logo.png"), f"Expected hyphenated logo, got {url}"
    assert "bottube_logo.png" not in url, "Underscore variant is 404; use hyphenated path"
