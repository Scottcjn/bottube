"""Unit tests for the BoTTube Python SDK."""

import json
import unittest
from unittest.mock import patch, MagicMock, mock_open

from bottube.client import BoTTubeClient, BoTTubeError


def _mock_response(data, status_code=200, ok=True):
    resp = MagicMock()
    resp.json.return_value = data
    resp.status_code = status_code
    resp.ok = ok
    resp.reason = "OK" if ok else "Error"
    resp.text = json.dumps(data)
    return resp


class TestBoTTubeClient(unittest.TestCase):
    def setUp(self):
        self.client = BoTTubeClient(
            base_url="https://bottube.ai", api_key="test-key"
        )

    def test_init_defaults(self):
        c = BoTTubeClient()
        self.assertEqual(c.base_url, "https://bottube.ai")
        self.assertIsNone(c.api_key)
        self.assertEqual(c.timeout, 30)

    def test_init_custom(self):
        c = BoTTubeClient(
            base_url="http://localhost:3000", api_key="abc", timeout=10
        )
        self.assertEqual(c.base_url, "http://localhost:3000")
        self.assertEqual(c.api_key, "abc")
        self.assertEqual(c.timeout, 10)

    def test_trailing_slash_stripped(self):
        c = BoTTubeClient(base_url="https://bottube.ai/")
        self.assertEqual(c.base_url, "https://bottube.ai")

    def test_stream_url(self):
        url = self.client.get_video_stream_url("abc123")
        self.assertEqual(url, "https://bottube.ai/api/videos/abc123/stream")

    @patch("bottube.client.requests.Session.request")
    def test_health_check(self, mock_request):
        mock_request.return_value = _mock_response(
            {"status": "ok", "timestamp": 123}
        )
        result = self.client.health_check()
        self.assertEqual(result["status"], "ok")
        mock_request.assert_called_once()

    @patch("bottube.client.requests.Session.request")
    def test_search(self, mock_request):
        mock_request.return_value = _mock_response({"videos": [], "total": 0})
        result = self.client.search("ai agents")
        self.assertIn("videos", result)

    @patch("bottube.client.requests.Session.request")
    def test_register(self, mock_request):
        mock_request.return_value = _mock_response(
            {"api_key": "new-key", "agent_name": "bot1"}
        )
        result = self.client.register("bot1", "Bot One")
        self.assertEqual(result["api_key"], "new-key")

    @patch("bottube.client.requests.Session.request")
    def test_list_videos(self, mock_request):
        mock_request.return_value = _mock_response(
            {"videos": [{"video_id": "v1"}], "total": 1}
        )
        result = self.client.list_videos(page=1, per_page=10)
        self.assertEqual(len(result["videos"]), 1)

    @patch("bottube.client.requests.Session.request")
    def test_get_video(self, mock_request):
        mock_request.return_value = _mock_response(
            {"video_id": "abc", "title": "Test"}
        )
        result = self.client.get_video("abc")
        self.assertEqual(result["video_id"], "abc")

    @patch("bottube.client.requests.Session.request")
    def test_comment(self, mock_request):
        mock_request.return_value = _mock_response(
            {"comment_id": 1, "content": "Nice!"}
        )
        result = self.client.comment("abc", "Nice!")
        self.assertEqual(result["comment_id"], 1)

    @patch("bottube.client.requests.Session.request")
    def test_vote(self, mock_request):
        mock_request.return_value = _mock_response(
            {"likes": 5, "dislikes": 0}
        )
        result = self.client.vote("abc", 1)
        self.assertEqual(result["likes"], 5)

    @patch("bottube.client.requests.Session.request")
    def test_like_shorthand(self, mock_request):
        mock_request.return_value = _mock_response({"likes": 1, "dislikes": 0})
        result = self.client.like("abc")
        self.assertEqual(result["likes"], 1)

    @patch("bottube.client.requests.Session.request")
    def test_delete(self, mock_request):
        mock_request.return_value = _mock_response({"deleted": True})
        result = self.client.delete("abc")
        self.assertTrue(result["deleted"])

    @patch("bottube.client.requests.Session.request")
    def test_api_error(self, mock_request):
        mock_request.return_value = _mock_response(
            {"error": "Not found"}, status_code=404, ok=False
        )
        with self.assertRaises(BoTTubeError) as ctx:
            self.client.get_video("nonexistent")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Not found", ctx.exception.error)

    @patch("bottube.client.requests.Session.request")
    def test_get_trending(self, mock_request):
        mock_request.return_value = _mock_response(
            {"videos": [], "total": 0}
        )
        result = self.client.get_trending(limit=5, timeframe="day")
        self.assertIn("videos", result)

    @patch("bottube.client.requests.Session.request")
    def test_get_feed(self, mock_request):
        mock_request.return_value = _mock_response(
            {"videos": [], "total": 0}
        )
        result = self.client.get_feed(page=1, per_page=10)
        self.assertIn("videos", result)

    @patch("bottube.client.requests.Session.request")
    def test_get_comments(self, mock_request):
        mock_request.return_value = _mock_response(
            {"comments": [{"id": 1, "content": "hi"}]}
        )
        result = self.client.get_comments("abc")
        self.assertEqual(len(result["comments"]), 1)

    @patch("bottube.client.requests.Session.request")
    def test_get_recent_comments(self, mock_request):
        mock_request.return_value = _mock_response(
            {"comments": [{"id": 1}]}
        )
        result = self.client.get_recent_comments(limit=5)
        self.assertEqual(len(result), 1)

    @patch("bottube.client.requests.Session.request")
    def test_comment_vote(self, mock_request):
        mock_request.return_value = _mock_response({"likes": 2, "dislikes": 0})
        result = self.client.comment_vote(1, 1)
        self.assertEqual(result["likes"], 2)

    @patch("bottube.client.requests.Session.request")
    def test_get_agent_profile(self, mock_request):
        mock_request.return_value = _mock_response(
            {"agent_name": "bot1", "display_name": "Bot One"}
        )
        result = self.client.get_agent_profile("bot1")
        self.assertEqual(result["agent_name"], "bot1")

    def test_error_construction(self):
        err = BoTTubeError(404, "Not found", {"error": "Not found"})
        self.assertEqual(err.status_code, 404)
        self.assertEqual(err.error, "Not found")
        self.assertIn("404", str(err))

    def test_list_videos_alias(self):
        """get_videos and list_videos should be the same underlying function."""
        self.assertEqual(
            BoTTubeClient.get_videos, BoTTubeClient.list_videos
        )


if __name__ == "__main__":
    unittest.main()
