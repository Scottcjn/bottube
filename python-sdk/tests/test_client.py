"""Unit tests for the BoTTube Python SDK."""

import json
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO

from bottube.client import BoTTubeClient, BoTTubeError


class TestBoTTubeClient(unittest.TestCase):
    def setUp(self):
        self.client = BoTTubeClient(base_url="https://bottube.ai", api_key="test-key")

    def test_init_defaults(self):
        c = BoTTubeClient()
        self.assertEqual(c.base_url, "https://bottube.ai")
        self.assertIsNone(c.api_key)
        self.assertEqual(c.timeout, 30)

    def test_init_custom(self):
        c = BoTTubeClient(base_url="http://localhost:3000", api_key="abc", timeout=10)
        self.assertEqual(c.base_url, "http://localhost:3000")
        self.assertEqual(c.api_key, "abc")
        self.assertEqual(c.timeout, 10)

    def test_trailing_slash_stripped(self):
        c = BoTTubeClient(base_url="https://bottube.ai/")
        self.assertEqual(c.base_url, "https://bottube.ai")

    def test_stream_url(self):
        url = self.client.get_video_stream_url("abc123")
        self.assertEqual(url, "https://bottube.ai/api/videos/abc123/stream")

    @patch("bottube.client.urlopen")
    def test_health_check(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"status": "ok", "timestamp": 123}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = self.client.health_check()
        self.assertEqual(result["status"], "ok")

    @patch("bottube.client.urlopen")
    def test_search(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"videos": [], "total": 0}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = self.client.search("ai agents")
        self.assertIn("videos", result)

    def test_error_construction(self):
        err = BoTTubeError(404, "Not found", {"error": "Not found"})
        self.assertEqual(err.status_code, 404)
        self.assertEqual(err.error, "Not found")
        self.assertIn("404", str(err))


if __name__ == "__main__":
    unittest.main()
