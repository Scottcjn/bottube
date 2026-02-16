"""Tests for API client."""

import pytest
from requests_mock import Mocker

from bottube_cli.client import BoTTubeClient


@pytest.fixture
def client():
    """Create client with test API key."""
    return BoTTubeClient("test_api_key")


def test_client_initialization(client):
    """Test client initialization."""
    assert client.api_key == "test_api_key"
    assert "X-API-Key" in client.session.headers
    assert client.session.headers["X-API-Key"] == "test_api_key"


def test_get_agent_info(requests_mock: Mocker, client):
    """Test getting agent information."""
    mock_response = {
        "agent_name": "test-agent",
        "display_name": "Test Agent",
        "id": "123"
    }

    requests_mock.get(
        "https://bottube.ai/api/agents/me",
        json=mock_response
    )

    agent = client.get_agent_info()

    assert agent == mock_response
    assert agent["agent_name"] == "test-agent"


def test_list_videos(requests_mock: Mocker, client):
    """Test listing videos."""
    mock_videos = [
        {"video_id": "1", "title": "Video 1"},
        {"video_id": "2", "title": "Video 2"}
    ]

    requests_mock.get(
        "https://bottube.ai/api/videos",
        json=mock_videos
    )

    videos = client.list_videos()

    assert len(videos) == 2
    assert videos[0]["title"] == "Video 1"


def test_list_videos_with_filters(requests_mock: Mocker, client):
    """Test listing videos with filters."""
    mock_videos = [
        {"video_id": "1", "title": "Tech Video", "agent": "tech-agent"}
    ]

    requests_mock.get(
        "https://bottube.ai/api/videos",
        json=mock_videos
    )

    videos = client.list_videos(agent="tech-agent", category="tech")

    assert len(videos) == 1
    # Verify params were sent
    assert requests_mock.called
    assert requests_mock.last_request.qs == {'agent': ['tech-agent'], 'category': ['tech']}


def test_search_videos(requests_mock: Mocker, client):
    """Test searching videos."""
    mock_videos = [
        {"video_id": "1", "title": "RustChain Mining", "description": "Mining tutorial"},
        {"video_id": "2", "title": "Other Video", "description": "Not related"}
    ]

    requests_mock.get(
        "https://bottube.ai/api/videos",
        json=mock_videos
    )

    videos = client.search_videos("mining")

    assert len(videos) == 1
    assert videos[0]["title"] == "RustChain Mining"


def test_upload_video(requests_mock: Mocker, client, tmp_path):
    """Test uploading a video."""
    mock_response = {
        "video_id": "test123",
        "watch_url": "/watch/test123",
        "ok": True
    }

    requests_mock.post(
        "https://bottube.ai/api/upload",
        json=mock_response
    )

    # Create test video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")

    result = client.upload_video(
        video_file=video_file,
        title="Test Upload",
        description="Test Description"
    )

    assert result["ok"] is True
    assert result["video_id"] == "test123"
    assert requests_mock.called
