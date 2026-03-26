# SPDX-License-Identifier: MIT
"""Tests for telegram_bot.py — BoTTube Telegram Bot."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram_bot import (
    BoTTubeAPI,
    Video,
    Agent,
    _escape,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_video(**kwargs):
    defaults = dict(
        id="v1", title="Test Video", description="A great video about testing",
        views=100, likes=10, thumbnail="https://img.test/thumb.jpg",
        agent_name="TestBot", duration=60.0, created_at="2026-01-01",
    )
    defaults.update(kwargs)
    return Video(**defaults)


def make_agent(**kwargs):
    defaults = dict(
        name="testbot", display_name="TestBot",
        bio="I make test videos", avatar_url="", video_count=42,
    )
    defaults.update(kwargs)
    return Agent(**defaults)


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


# ---------------------------------------------------------------------------
# Video model
# ---------------------------------------------------------------------------

class TestVideo:
    def test_url(self):
        v = make_video(id="abc123")
        assert v.url == "https://bottube.ai/watch/abc123"

    def test_short_desc_truncation(self):
        v = make_video(description="x" * 200)
        assert len(v.short_desc) <= 124

    def test_short_desc_no_truncation(self):
        v = make_video(description="Short desc")
        assert v.short_desc == "Short desc"

    def test_to_text(self):
        v = make_video(title="My Video", agent_name="Bot", views=50, likes=5)
        text = v.to_text(1)
        assert "My Video" in text
        assert "Bot" in text
        assert "50" in text

    def test_to_text_escapes_html(self):
        v = make_video(title="<script>alert(1)</script>")
        text = v.to_text()
        assert "<script>" not in text
        assert "&lt;script&gt;" in text


# ---------------------------------------------------------------------------
# Agent model
# ---------------------------------------------------------------------------

class TestAgent:
    def test_to_text(self):
        a = make_agent(display_name="CosmoBot", bio="Space videos", video_count=100)
        text = a.to_text()
        assert "CosmoBot" in text
        assert "100 videos" in text

    def test_to_text_url(self):
        a = make_agent(name="cosmo bot")
        text = a.to_text()
        assert "cosmo%20bot" in text


# ---------------------------------------------------------------------------
# HTML escaping
# ---------------------------------------------------------------------------

class TestEscape:
    def test_escapes_lt_gt(self):
        assert _escape("<b>") == "&lt;b&gt;"

    def test_escapes_ampersand(self):
        assert _escape("A & B") == "A &amp; B"

    def test_clean_text_unchanged(self):
        assert _escape("Hello World") == "Hello World"


# ---------------------------------------------------------------------------
# BoTTubeAPI
# ---------------------------------------------------------------------------

class TestBoTTubeAPI:
    @patch("telegram_bot.requests.Session")
    def test_latest(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = MockResponse({
            "videos": [
                {"video_id": "v1", "title": "Latest", "views": 10,
                 "agent_name": "Bot", "likes": 1, "thumbnail": "",
                 "description": "", "duration_sec": 30, "created_at": "2026"},
            ]
        })

        api = BoTTubeAPI("http://test")
        videos = api.latest(5)
        assert len(videos) == 1
        assert videos[0].title == "Latest"

    @patch("telegram_bot.requests.Session")
    def test_search(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = MockResponse([
            {"video_id": "v1", "title": "Found It", "views": 5,
             "agent_name": "Bot", "likes": 0, "thumbnail": "",
             "description": "match", "duration_sec": 10, "created_at": "2026"},
        ])

        api = BoTTubeAPI("http://test")
        videos = api.search("test")
        assert len(videos) == 1
        assert videos[0].title == "Found It"

    @patch("telegram_bot.requests.Session")
    def test_get_video(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = MockResponse({
            "video_id": "v1", "title": "Single", "views": 100,
            "agent_name": "Bot", "likes": 5, "thumbnail": "t.jpg",
            "description": "Desc", "duration_sec": 120, "created_at": "2026",
        })

        api = BoTTubeAPI("http://test")
        video = api.get_video("v1")
        assert video is not None
        assert video.title == "Single"
        assert video.views == 100

    @patch("telegram_bot.requests.Session")
    def test_get_video_not_found(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = MockResponse({}, 404)

        api = BoTTubeAPI("http://test")
        video = api.get_video("nonexistent")
        assert video is None

    @patch("telegram_bot.requests.Session")
    def test_get_agent(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = MockResponse({
            "agent_name": "cosmo", "display_name": "CosmoBot",
            "bio": "Space stuff", "avatar_url": "", "video_count": 42,
        })

        api = BoTTubeAPI("http://test")
        agent = api.get_agent("cosmo")
        assert agent is not None
        assert agent.name == "cosmo"
        assert agent.video_count == 42

    @patch("telegram_bot.requests.Session")
    def test_items_handles_list(self, mock_session_cls):
        api = BoTTubeAPI("http://test")
        assert api._items([1, 2, 3]) == [1, 2, 3]

    @patch("telegram_bot.requests.Session")
    def test_items_handles_dict_with_videos(self, mock_session_cls):
        api = BoTTubeAPI("http://test")
        assert api._items({"videos": [1]}) == [1]

    @patch("telegram_bot.requests.Session")
    def test_items_handles_dict_with_data(self, mock_session_cls):
        api = BoTTubeAPI("http://test")
        assert api._items({"data": [2]}) == [2]


# ---------------------------------------------------------------------------
# Integration-style tests
# ---------------------------------------------------------------------------

class TestBotIntegration:
    def test_video_list_formatting(self):
        """Test that a list of videos formats correctly."""
        videos = [
            make_video(id=f"v{i}", title=f"Video {i}", views=i * 10)
            for i in range(1, 6)
        ]
        lines = ["📺 <b>Latest Videos</b>\n"]
        for i, v in enumerate(videos, 1):
            lines.append(v.to_text(i))
        result = "\n\n".join(lines)
        assert "Video 1" in result
        assert "Video 5" in result
        assert result.count("🎬") == 5

    def test_agent_with_videos_formatting(self):
        agent = make_agent(display_name="CosmoBot", video_count=100)
        videos = [make_video(title=f"Vid {i}") for i in range(3)]

        lines = [agent.to_text()]
        lines.append("\n📺 <b>Recent uploads:</b>")
        for i, v in enumerate(videos, 1):
            lines.append(v.to_text(i))

        result = "\n\n".join(lines)
        assert "CosmoBot" in result
        assert "Vid 0" in result
