# SPDX-License-Identifier: MIT
"""Regression: every published logo URL must resolve to a deployed static asset.

Both the RSS channel image and the news-article JSON-LD publisher logo point at
``https://bottube.ai/static/bottube-logo.png``. The underscore variant
(``bottube`` + ``_logo.png``) is not shipped in ``bottube_static/``, so any
surface that emits it publishes an image URL that 404s.
"""

import json
import re
import time
from pathlib import Path

from flask import Flask, render_template

import news_routes

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "bottube_templates"
STATIC_DIR = REPO_ROOT / "bottube_static"

DEPLOYED_ASSET = "bottube-logo.png"
# Joined at runtime so this guard never trips on its own source.
UNDEPLOYED_ASSET = "bottube" + "_logo.png"


class Row(dict):
    def __getitem__(self, key):
        return self.get(key)


def _news_row(**overrides):
    row = Row(
        video_id="news-logo-1",
        title="Storm update",
        description="Weather and climate briefing",
        created_at=time.time(),
        thumbnail="thumb.jpg",
        duration_sec=8,
        views=1,
        category="weather",
        agent_name="the_daily_byte",
        display_name="Daily Byte",
        avatar_url="",
    )
    row.update(overrides)
    return row


def _published_sources():
    """Route modules and templates, i.e. the files that emit user-facing URLs."""
    sources = sorted(REPO_ROOT.glob("*.py"))
    sources += sorted(TEMPLATE_DIR.glob("*.html"))
    return sources


def _deployed_url_from_rss(monkeypatch):
    monkeypatch.setattr(news_routes, "_get_news_videos", lambda _limit=30: [_news_row()])
    monkeypatch.setattr(news_routes, "_get_weather_videos", lambda _limit=20: [])

    app = Flask(__name__)
    app.register_blueprint(news_routes.news_bp)

    response = app.test_client().get("/news/rss")

    assert response.status_code == 200
    match = re.search(r"<url>(https://bottube\.ai/static/[^<]+)</url>", response.text)
    assert match, "RSS feed missing <image><url>"
    return match.group(1)


def test_deployed_logo_asset_exists():
    assert (STATIC_DIR / DEPLOYED_ASSET).is_file(), (
        "the logo URL published by the RSS channel and news JSON-LD must be a "
        "shipped asset"
    )


def test_news_rss_channel_logo_url_resolves(monkeypatch):
    url = _deployed_url_from_rss(monkeypatch)

    assert url.endswith(DEPLOYED_ASSET), f"Expected hyphenated logo, got {url}"
    assert (STATIC_DIR / url.rsplit("/", 1)[-1]).is_file(), (
        f"RSS channel image URL is not deployed: {url}"
    )


def test_news_article_publisher_logo_url_resolves(app):
    # Rendered through the real application so the page's Jinja filters and
    # globals resolve exactly as they do in production.
    with app.test_request_context():
        html = render_template("news_article.html", video=_news_row())

    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )
    assert blocks, "news article page is missing its JSON-LD block"

    structured = json.loads(blocks[0])
    logo_url = structured["publisher"]["logo"]["url"]

    assert logo_url.endswith(DEPLOYED_ASSET), (
        f"publisher logo URL must use the deployed asset, got {logo_url}"
    )
    assert (STATIC_DIR / logo_url.rsplit("/", 1)[-1]).is_file(), (
        f"news article publishes a 404 publisher logo: {logo_url}"
    )


def test_no_published_source_references_undeployed_logo_variant():
    offenders = []

    for path in _published_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if UNDEPLOYED_ASSET in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, (
        f"{UNDEPLOYED_ASSET} is not deployed; use {DEPLOYED_ASSET} instead: "
        + ", ".join(offenders)
    )
