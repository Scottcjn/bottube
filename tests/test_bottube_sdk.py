# SPDX-License-Identifier: MIT
"""
Tests for the BoTTube Python SDK.

Uses unittest.mock to avoid requiring a live BoTTube server.
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest

from bottube_sdk import BoTTubeClient
from bottube_sdk.client import (
    AuthenticationError,
    BoTTubeError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return BoTTubeClient(api_key="test-key-123", base_url="https://bottube.test")


@pytest.fixture
def public_client():
    return BoTTubeClient(base_url="https://bottube.test")


def _mock_response(status_code=200, json_data=None, text=""):
    """Build a mock requests.Response with a status code and JSON payload."""
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

class TestAuthentication:
    def test_api_key_from_constructor(self):
        """API key passed to the constructor is stored on the client."""
        c = BoTTubeClient(api_key="abc", base_url="http://x")
        assert c.api_key == "abc"

    def test_api_key_from_env(self, monkeypatch):
        """BOTTUBE_API_KEY env var is picked up when no key is passed."""
        monkeypatch.setenv("BOTTUBE_API_KEY", "env-key")
        c = BoTTubeClient(base_url="http://x")
        assert c.api_key == "env-key"

    def test_missing_api_key_raises_on_auth(self, public_client):
        """Requesting auth headers without a key raises AuthenticationError."""
        with pytest.raises(AuthenticationError, match="API key required"):
            public_client._headers(auth=True)

    def test_api_key_sent_in_header(self, client):
        """Authenticated requests send the key as X-API-Key."""
        hdrs = client._headers(auth=True)
        assert hdrs["X-API-Key"] == "test-key-123"

    def test_public_headers_no_key(self, public_client):
        """Unauthenticated requests omit the X-API-Key header."""
        hdrs = public_client._headers(auth=False)
        assert "X-API-Key" not in hdrs


# ---------------------------------------------------------------------------
# Video operations tests
# ---------------------------------------------------------------------------

class TestVideoOperations:
    def test_get_video(self, client):
        """get_video returns the parsed video payload on 200."""
        mock_resp = _mock_response(200, {"video_id": "abc", "title": "Test"})
        with patch("bottube_sdk.client.requests.Session.get", return_value=mock_resp):
            result = client.get_video("abc")
        assert result["video_id"] == "abc"

    def test_get_video_not_found(self, client):
        """get_video raises NotFoundError on 404."""
        mock_resp = _mock_response(404, {"error": "Video not found"})
        with patch("bottube_sdk.client.requests.Session.get", return_value=mock_resp):
            with pytest.raises(NotFoundError):
                client.get_video("nonexistent")

    def test_list_videos(self, client):
        """list_videos forwards page/sort params and returns the payload."""
        mock_resp = _mock_response(200, {"videos": [], "page": 1})
        with patch("bottube_sdk.client.requests.Session.get", return_value=mock_resp) as mock_get:
            result = client.list_videos(page=2, sort="views")
        assert result["page"] == 1
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["page"] == 2
        assert call_kwargs["params"]["sort"] == "views"

    def test_search_videos(self, client):
        """search forwards the query and category filters."""
        mock_resp = _mock_response(200, {"results": [], "count": 0})
        with patch("bottube_sdk.client.requests.Session.get", return_value=mock_resp) as mock_get:
            result = client.search("retro computing", category="retro")
        assert result["count"] == 0
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["q"] == "retro computing"

    def test_upload_video_file_not_found(self, client):
        """upload raises FileNotFoundError for a missing file path."""
        with pytest.raises(FileNotFoundError):
            client.upload("/nonexistent/video.mp4")

    def test_upload_invalid_format(self, client):
        """upload rejects non-video file extensions with ValidationError."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not a video")
            path = f.name
        try:
            with pytest.raises(ValidationError, match="Invalid video format"):
                client.upload(path, title="Bad format")
        finally:
            os.unlink(path)

    def test_delete_video(self, client):
        """delete_video issues DELETE and returns the server payload."""
        mock_resp = _mock_response(200, {"status": "deleted"})
        with patch("bottube_sdk.client.requests.Session.delete", return_value=mock_resp):
            result = client.delete_video("abc")
        assert result["status"] == "deleted"


# ---------------------------------------------------------------------------
# Comment operations tests
# ---------------------------------------------------------------------------

class TestCommentOperations:
    def test_comment(self, client):
        """comment posts content with the default comment_type."""
        mock_resp = _mock_response(200, {"id": 1, "content": "Nice!"})
        with patch("bottube_sdk.client.requests.Session.post", return_value=mock_resp) as mock_post:
            result = client.comment("abc", "Nice!")
        assert result["content"] == "Nice!"
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["comment_type"] == "comment"

    def test_get_comments(self, client):
        """get_comments returns the comments collection for a video."""
        mock_resp = _mock_response(200, {"comments": []})
        with patch("bottube_sdk.client.requests.Session.get", return_value=mock_resp):
            result = client.get_comments("abc")
        assert "comments" in result

    def test_recent_comments(self, client):
        """recent_comments forwards since/limit params."""
        mock_resp = _mock_response(200, {"comments": []})
        with patch("bottube_sdk.client.requests.Session.get", return_value=mock_resp) as mock_get:
            result = client.recent_comments(since=1000, limit=10)
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["since"] == 1000
        assert call_kwargs["params"]["limit"] == 10


# ---------------------------------------------------------------------------
# Vote operations tests
# ---------------------------------------------------------------------------

class TestVoteOperations:
    def test_vote_video_like(self, client):
        """vote_video sends vote=1 for a like."""
        mock_resp = _mock_response(200, {"status": "voted"})
        with patch("bottube_sdk.client.requests.Session.post", return_value=mock_resp) as mock_post:
            result = client.vote_video("abc", 1)
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["vote"] == 1

    def test_vote_video_invalid(self, client):
        """vote_video rejects values outside -1/1 with ValidationError."""
        with pytest.raises(ValidationError, match="vote must be"):
            client.vote_video("abc", 5)

    def test_vote_comment(self, client):
        """vote_comment votes on a comment by id."""
        mock_resp = _mock_response(200, {"status": "voted"})
        with patch("bottube_sdk.client.requests.Session.post", return_value=mock_resp):
            result = client.vote_comment(42, 1)

    def test_vote_comment_invalid(self, client):
        """vote_comment rejects invalid vote values."""
        with pytest.raises(ValidationError, match="vote must be"):
            client.vote_comment(42, 2)

    def test_like_video_shorthand(self, client):
        """like_video is shorthand for vote_video with vote=1."""
        mock_resp = _mock_response(200, {"status": "voted"})
        with patch("bottube_sdk.client.requests.Session.post", return_value=mock_resp) as mock_post:
            client.like_video("abc")
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["vote"] == 1

    def test_dislike_video_shorthand(self, client):
        """dislike_video is shorthand for vote_video with vote=-1."""
        mock_resp = _mock_response(200, {"status": "voted"})
        with patch("bottube_sdk.client.requests.Session.post", return_value=mock_resp) as mock_post:
            client.dislike_video("abc")
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["vote"] == -1


# ---------------------------------------------------------------------------
# Tip operations tests
# ---------------------------------------------------------------------------

class TestTipOperations:
    def test_tip_video(self, client):
        """tip_video sends the RTC amount and optional message."""
        mock_resp = _mock_response(200, {"status": "tipped"})
        with patch("bottube_sdk.client.requests.Session.post", return_value=mock_resp) as mock_post:
            result = client.tip_video("abc", 0.5, message="Nice work!")
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["amount"] == 0.5
        assert call_kwargs["json"]["message"] == "Nice work!"

    def test_get_video_tips(self, client):
        """get_video_tips returns the tips collection for a video."""
        mock_resp = _mock_response(200, {"tips": []})
        with patch("bottube_sdk.client.requests.Session.get", return_value=mock_resp):
            result = client.get_video_tips("abc")
        assert "tips" in result


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_rate_limit_error(self, client):
        """A 429 response maps to RateLimitError."""
        mock_resp = _mock_response(429, {"error": "Rate limit exceeded"})
        with patch("bottube_sdk.client.requests.Session.get", return_value=mock_resp):
            with pytest.raises(RateLimitError):
                client.get_video("abc")

    def test_auth_error(self, public_client):
        """A 401 response maps to AuthenticationError."""
        mock_resp = _mock_response(401, {"error": "Invalid API key"})
        with patch("bottube_sdk.client.requests.Session.get", return_value=mock_resp):
            with pytest.raises(AuthenticationError):
                public_client.list_videos()

    def test_server_error(self, client):
        """A 5xx response maps to BoTTubeError with the server message."""
        mock_resp = _mock_response(500, {"error": "Internal server error"})
        with patch("bottube_sdk.client.requests.Session.get", return_value=mock_resp):
            with pytest.raises(BoTTubeError, match="Internal server error"):
                client.get_video("abc")

    def test_validation_error_on_400(self, client):
        """A 400 response maps to ValidationError."""
        mock_resp = _mock_response(400, {"error": "Bad request"})
        with patch("bottube_sdk.client.requests.Session.post", return_value=mock_resp):
            with pytest.raises(ValidationError):
                client.comment("abc", "test")


# ---------------------------------------------------------------------------
# URL construction tests
# ---------------------------------------------------------------------------

class TestURLConstruction:
    def test_base_url_trailing_slash_stripped(self):
        """Trailing slashes are stripped from the base URL."""
        c = BoTTubeClient(base_url="https://bottube.test/")
        assert c.base_url == "https://bottube.test"

    def test_url_building(self, client):
        """_url joins the base URL with the API path."""
        assert client._url("/api/videos/abc") == "https://bottube.test/api/videos/abc"

    def test_base_url_from_env(self, monkeypatch):
        """BOTTUBE_BASE_URL env var overrides the default base URL."""
        monkeypatch.setenv("BOTTUBE_BASE_URL", "https://custom.test")
        c = BoTTubeClient()
        assert c.base_url == "https://custom.test"
