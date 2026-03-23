#!/usr/bin/env python3
"""
Tests for BoTTube Telegram Bot.

Run: python3 -m pytest tests/test_telegram_bot.py -v
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import bottube_telegram_bot as bot


class TestFormatVideo(unittest.TestCase):
    """Test video formatting."""

    def test_basic_format(self):
        v = {"id": "abc", "title": "Test Video", "agent_name": "agent1", "views": 100, "likes": 5}
        result = bot.format_video(v, index=1)
        self.assertIn("Test Video", result)
        self.assertIn("agent1", result)
        self.assertIn("100", result)
        self.assertIn("bottube.ai/watch/abc", result)

    def test_format_with_duration(self):
        v = {"id": "1", "title": "T", "agent_name": "a", "views": 0, "likes": 0, "duration": "2:30"}
        result = bot.format_video(v, index=1)
        self.assertIn("2:30", result)

    def test_format_no_index(self):
        v = {"id": "1", "title": "T", "agent_name": "a", "views": 0, "likes": 0}
        result = bot.format_video(v, index=0)
        self.assertNotIn("<b>0.</b>", result)

    def test_html_escaping(self):
        v = {"id": "1", "title": "Test <script>alert(1)</script>", "agent_name": "a", "views": 0, "likes": 0}
        result = bot.format_video(v)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_missing_fields(self):
        v = {"id": "1"}
        result = bot.format_video(v)
        self.assertIn("Untitled", result)
        self.assertIn("unknown", result)

    def test_video_id_fallback(self):
        v = {"video_id": "xyz", "title": "T", "agent_name": "a", "views": 0, "likes": 0}
        result = bot.format_video(v)
        self.assertIn("xyz", result)

    def test_agent_field_fallback(self):
        v = {"id": "1", "title": "T", "agent": "fallback-agent", "views": 0, "likes": 0}
        result = bot.format_video(v)
        self.assertIn("fallback-agent", result)


class TestFormatVideoList(unittest.TestCase):
    """Test video list formatting."""

    def test_empty_list(self):
        result = bot.format_video_list([], "Header")
        self.assertIn("No videos found", result)
        self.assertIn("Header", result)

    def test_with_videos(self):
        videos = [
            {"id": "1", "title": "Video 1", "agent_name": "a", "views": 10, "likes": 1},
            {"id": "2", "title": "Video 2", "agent_name": "b", "views": 20, "likes": 2},
        ]
        result = bot.format_video_list(videos, "Test")
        self.assertIn("Video 1", result)
        self.assertIn("Video 2", result)
        self.assertIn("<b>Test</b>", result)

    def test_no_header(self):
        videos = [{"id": "1", "title": "V", "agent_name": "a", "views": 0, "likes": 0}]
        result = bot.format_video_list(videos)
        self.assertIn("V", result)


class TestApiHelpers(unittest.TestCase):
    """Test API helper functions."""

    @patch("bottube_telegram_bot.requests.get")
    def test_get_videos_list_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"id": "1", "title": "A"},
            {"id": "2", "title": "B"},
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        videos = bot.get_videos(limit=5)
        self.assertEqual(len(videos), 2)

    @patch("bottube_telegram_bot.requests.get")
    def test_get_videos_dict_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"videos": [{"id": "1"}]}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        videos = bot.get_videos()
        self.assertEqual(len(videos), 1)

    @patch("bottube_telegram_bot.requests.get")
    def test_get_videos_error(self, mock_get):
        mock_get.side_effect = Exception("timeout")
        videos = bot.get_videos()
        self.assertEqual(videos, [])

    @patch("bottube_telegram_bot.requests.get")
    def test_search_videos(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "1", "title": "match"}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        videos = bot.search_videos("test")
        self.assertEqual(len(videos), 1)
        mock_get.assert_called_once()

    @patch("bottube_telegram_bot.requests.get")
    def test_get_video_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "abc", "title": "T"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        video = bot.get_video("abc")
        self.assertIsNotNone(video)
        self.assertEqual(video["id"], "abc")

    @patch("bottube_telegram_bot.requests.get")
    def test_get_video_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": "not found"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        video = bot.get_video("nonexistent")
        self.assertIsNone(video)

    @patch("bottube_telegram_bot.requests.get")
    def test_get_agent(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"name": "sophia", "display_name": "Sophia Elya"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        agent = bot.get_agent("sophia")
        self.assertIsNotNone(agent)
        self.assertEqual(agent["name"], "sophia")

    @patch("bottube_telegram_bot.requests.get")
    def test_get_agent_videos(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "v1"}, {"id": "v2"}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        videos = bot.get_agent_videos("sophia")
        self.assertEqual(len(videos), 2)

    @patch("bottube_telegram_bot.requests.get")
    def test_api_get_none_on_error(self, mock_get):
        mock_get.side_effect = Exception("connection refused")
        result = bot.api_get("/test")
        self.assertIsNone(result)

    @patch("bottube_telegram_bot.requests.get")
    def test_limit_respected(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": str(i)} for i in range(20)]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        videos = bot.get_videos(limit=3)
        self.assertEqual(len(videos), 3)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and robustness."""

    def test_format_video_special_chars(self):
        v = {"id": "1", "title": "Test & \"quotes\" <tags>", "agent_name": "a&b", "views": 0, "likes": 0}
        result = bot.format_video(v)
        self.assertIn("&amp;", result)
        self.assertNotIn('"quotes"', result)

    @patch("bottube_telegram_bot.requests.get")
    def test_search_empty_result(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        videos = bot.search_videos("nonexistent12345")
        self.assertEqual(videos, [])

    @patch("bottube_telegram_bot.requests.get")
    def test_get_agent_fallback_to_list(self, mock_get):
        """When direct agent lookup fails, falls back to search."""
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_resp = MagicMock()
            if call_count[0] == 1:
                mock_resp.json.return_value = {"error": "not found"}
            else:
                mock_resp.json.return_value = [{"name": "found-agent"}]
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        mock_get.side_effect = side_effect
        agent = bot.get_agent("test")
        self.assertIsNotNone(agent)


if __name__ == "__main__":
    unittest.main()
