# SPDX-License-Identifier: MIT
"""Unit tests for the BoTTube Python SDK."""

import json
import os
import tempfile
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

    @patch("bottube.client.urlopen")
    def test_streaming_upload_keeps_request_body_lazy(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = b'{"video_id":"uploaded"}'
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        captured = {}

        def consume(request, timeout):
            self.assertNotIsInstance(request.data, (bytes, bytearray))
            parts = list(request.data)
            captured["parts"] = parts
            captured["content_length"] = int(request.get_header("Content-length"))
            return response

        mock_urlopen.side_effect = consume

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as upload:
            upload.write(b"0123456789")
            upload_path = upload.name

        try:
            result = self.client._streaming_upload(
                "/api/upload", upload_path, {"title": "Chunked"}, chunk_size=3
            )
        finally:
            os.unlink(upload_path)

        body = b"".join(captured["parts"])
        file_chunks = [part for part in captured["parts"] if part in {b"012", b"345", b"678", b"9"}]
        self.assertEqual(file_chunks, [b"012", b"345", b"678", b"9"])
        self.assertIn(b"0123456789", body)
        self.assertEqual(captured["content_length"], len(body))
        self.assertEqual(result, {"video_id": "uploaded"})


if __name__ == "__main__":
    unittest.main()
