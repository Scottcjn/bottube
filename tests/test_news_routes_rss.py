# SPDX-License-Identifier: MIT
"""RSS rendering tests for news routes."""

import time
import xml.etree.ElementTree as ET

from flask import Flask

import news_routes


class Row(dict):
    def __getitem__(self, key):
        return self.get(key)


def test_news_rss_escapes_category_xml(monkeypatch):
    row = Row(
        video_id="news-1",
        title="Storm update",
        description="Weather and climate briefing",
        created_at=time.time(),
        thumbnail="thumb.jpg",
        duration_sec=8,
        views=1,
        category="weather & climate <alerts>",
        agent_name="the_daily_byte",
        display_name="Daily Byte",
        avatar_url="",
    )
    monkeypatch.setattr(news_routes, "_get_news_videos", lambda _limit=30: [row])
    monkeypatch.setattr(news_routes, "_get_weather_videos", lambda _limit=20: [])

    app = Flask(__name__)
    app.register_blueprint(news_routes.news_bp)

    response = app.test_client().get("/news/rss")

    assert response.status_code == 200
    ET.fromstring(response.text)
    assert "<category>weather &amp; climate &lt;alerts&gt;</category>" in response.text
