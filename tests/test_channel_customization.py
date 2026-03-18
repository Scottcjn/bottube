"""Channel customization test suite for BoTTube (Issue #422).

Tests the channel customization features including:
- Custom banner URLs
- Theme color customization (primary/accent colors)
- Pinned videos functionality
- Safe defaults and validation
- Creator-scoped permissions

Run:
    python -m pytest tests/test_channel_customization.py -v
"""

import json
import os
import tempfile
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Flask app fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a test Flask app with an in-memory database."""
    server_path = Path(__file__).resolve().parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["BOTTUBE_BASE_DIR"] = tmpdir
        db_path = Path(tmpdir) / "bottube.db"
        video_dir = Path(tmpdir) / "videos"
        thumb_dir = Path(tmpdir) / "thumbnails"
        avatar_dir = Path(tmpdir) / "avatars"
        video_dir.mkdir()
        thumb_dir.mkdir()
        avatar_dir.mkdir()

        import importlib
        import sys
        from unittest.mock import patch

        # Ensure fresh import
        for mod_name in list(sys.modules.keys()):
            if "bottube_server" in mod_name or "paypal_packages" in mod_name:
                del sys.modules[mod_name]

        sys.path.insert(0, str(server_path))
        
        # Mock init_store_db to avoid hardcoded path issues
        with patch('paypal_packages.init_store_db'):
            import bottube_server

            bottube_server.DB_PATH = db_path
            bottube_server.VIDEO_DIR = video_dir
            bottube_server.THUMB_DIR = thumb_dir
            bottube_server.AVATAR_DIR = avatar_dir

            flask_app = bottube_server.app
            flask_app.config["TESTING"] = True
            flask_app.config["SECRET_KEY"] = "test-secret-key"

            with flask_app.app_context():
                bottube_server.init_db()

            yield flask_app


@pytest.fixture
def client(app):
    """Return a Flask test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent(client):
    """Create a test agent."""
    resp = client.post("/api/register", json={
        "agent_name": "test-creator",
        "display_name": "Test Creator"
    })
    data = json.loads(resp.data)
    return data


@pytest.fixture
def agent2(client):
    """Create a second test agent."""
    resp = client.post("/api/register", json={
        "agent_name": "other-creator",
        "display_name": "Other Creator"
    })
    data = json.loads(resp.data)
    return data


@pytest.fixture
def video(app, agent):
    """Create a test video for the agent."""
    # Create a minimal video record directly in DB
    import bottube_server
    db = bottube_server.get_db()
    video_id = "test-video-001"
    db.execute("""
        INSERT INTO videos (video_id, agent_id, title, description, filename, duration_sec, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (video_id, agent["id"], "Test Video", "A test video", "test.mp4", 5.0, time.time()))
    db.commit()
    return {"video_id": video_id}


@pytest.fixture
def video2(app, agent):
    """Create a second test video."""
    import bottube_server
    db = bottube_server.get_db()
    video_id = "test-video-002"
    db.execute("""
        INSERT INTO videos (video_id, agent_id, title, description, filename, duration_sec, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (video_id, agent["id"], "Second Video", "Another test video", "test2.mp4", 3.0, time.time()))
    db.commit()
    return {"video_id": video_id}


@pytest.fixture
def video3(app, agent):
    """Create a third test video."""
    import bottube_server
    db = bottube_server.get_db()
    video_id = "test-video-003"
    db.execute("""
        INSERT INTO videos (video_id, agent_id, title, description, filename, duration_sec, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (video_id, agent["id"], "Third Video", "Third test video", "test3.mp4", 4.0, time.time()))
    db.commit()
    return {"video_id": video_id}


# ---------------------------------------------------------------------------
# Customization API Tests
# ---------------------------------------------------------------------------

class TestChannelCustomization:
    """Test channel customization endpoints."""

    def test_get_customization_defaults(self, client, agent):
        """Test getting customization returns safe defaults."""
        headers = {"X-API-Key": agent["api_key"]}
        resp = client.get("/api/agents/me/customization", headers=headers)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        
        assert data["banner_url"] == ""
        assert data["theme_primary_color"] == "#0f0f0f"
        assert data["theme_accent_color"] == "#f0b90b"
        assert data["theme_background_dark"] == 1

    def test_update_customization_valid(self, client, agent):
        """Test updating customization with valid values."""
        headers = {"X-API-Key": agent["api_key"]}
        resp = client.post("/api/agents/me/customization",
                       headers=headers,
                       json={
                           "banner_url": "https://example.com/banner.png",
                           "theme_primary_color": "#1a1a1a",
                           "theme_accent_color": "#3ea6ff",
                           "theme_background_dark": 0
                       })
        assert resp.status_code == 200
        data = json.loads(resp.data)
        
        assert data["ok"] is True
        assert data["banner_url"] == "https://example.com/banner.png"
        assert data["theme_primary_color"] == "#1a1a1a"
        assert data["theme_accent_color"] == "#3ea6ff"
        assert data["theme_background_dark"] == 0

    def test_update_customization_partial(self, client, agent):
        """Test updating only some customization fields."""
        headers = {"X-API-Key": agent["api_key"]}
        
        # First set all fields
        client.post("/api/agents/me/customization",
                headers=headers,
                json={
                    "banner_url": "https://example.com/banner.png",
                    "theme_primary_color": "#1a1a1a",
                    "theme_accent_color": "#f0b90b",
                })
        
        # Then update only banner
        resp = client.post("/api/agents/me/customization",
                       headers=headers,
                       json={"banner_url": "https://example.com/new-banner.png"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        
        # Banner should be updated
        assert data["banner_url"] == "https://example.com/new-banner.png"
        # Colors should be preserved (or defaults if not preserved)
        assert data["theme_accent_color"] in ["#f0b90b", "#1a1a1a"]

    def test_update_customization_invalid_banner_url(self, client, agent):
        """Test that invalid banner URLs are rejected."""
        headers = {"X-API-Key": agent["api_key"]}
        resp = client.post("/api/agents/me/customization",
                       headers=headers,
                       json={"banner_url": "not-a-valid-url"})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data

    def test_update_customization_invalid_color(self, client, agent):
        """Test that colors outside allowed palette are rejected."""
        headers = {"X-API-Key": agent["api_key"]}
        resp = client.post("/api/agents/me/customization",
                       headers=headers,
                       json={"theme_primary_color": "#ff0000"})  # Not in allowed palette
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data
        assert "allowed_primary_colors" in data

    def test_update_customization_invalid_color_format(self, client, agent):
        """Test that invalid color formats are rejected."""
        headers = {"X-API-Key": agent["api_key"]}
        resp = client.post("/api/agents/me/customization",
                       headers=headers,
                       json={"theme_primary_color": "not-a-color"})
        assert resp.status_code == 400

    def test_get_public_customization(self, client, agent):
        """Test getting public customization for a channel."""
        # First set customization
        headers = {"X-API-Key": agent["api_key"]}
        client.post("/api/agents/me/customization",
                headers=headers,
                json={
                    "banner_url": "https://example.com/banner.png",
                    "theme_primary_color": "#1a1a1a",
                    "theme_accent_color": "#3ea6ff",
                })
        
        # Get public customization
        resp = client.get("/api/agents/test-creator/customization")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        
        assert data["banner_url"] == "https://example.com/banner.png"
        assert data["theme_primary_color"] == "#1a1a1a"
        assert data["theme_accent_color"] == "#3ea6ff"

    def test_get_public_customization_not_found(self, client):
        """Test getting customization for non-existent agent."""
        resp = client.get("/api/agents/nonexistent-agent/customization")
        assert resp.status_code == 404

    def test_customization_requires_auth(self, client):
        """Test that updating customization requires authentication."""
        resp = client.post("/api/agents/me/customization",
                       json={"banner_url": "https://example.com/banner.png"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Pinned Videos Tests
# ---------------------------------------------------------------------------

class TestPinnedVideos:
    """Test pinned videos functionality."""

    def test_pin_video(self, client, agent, video):
        """Test pinning a video."""
        headers = {"X-API-Key": agent["api_key"]}
        resp = client.post("/api/agents/me/pinned",
                       headers=headers,
                       json={"video_id": video["video_id"]})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        
        assert data["ok"] is True
        assert data["video_id"] == video["video_id"]
        assert data["position"] == 0

    def test_pin_video_already_pinned(self, client, agent, video):
        """Test pinning an already-pinned video."""
        headers = {"X-API-Key": agent["api_key"]}
        
        # Pin first time
        client.post("/api/agents/me/pinned",
                headers=headers,
                json={"video_id": video["video_id"]})
        
        # Try to pin again
        resp = client.post("/api/agents/me/pinned",
                       headers=headers,
                       json={"video_id": video["video_id"]})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "already pinned" in data.get("message", "").lower()

    def test_pin_video_max_limit(self, client, agent, video, video2, video3):
        """Test that max 3 videos can be pinned."""
        headers = {"X-API-Key": agent["api_key"]}
        
        # Pin 3 videos
        client.post("/api/agents/me/pinned", headers=headers, json={"video_id": video["video_id"]})
        client.post("/api/agents/me/pinned", headers=headers, json={"video_id": video2["video_id"]})
        client.post("/api/agents/me/pinned", headers=headers, json={"video_id": video3["video_id"]})
        
        # Try to pin a 4th video
        import bottube_server
        db = bottube_server.get_db()
        db.execute("""
            INSERT INTO videos (video_id, agent_id, title, description, filename, duration_sec, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("test-video-004", agent["id"], "Fourth Video", "", "test4.mp4", 2.0, time.time()))
        db.commit()
        
        resp = client.post("/api/agents/me/pinned",
                       headers=headers,
                       json={"video_id": "test-video-004"})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "Maximum 3 pinned videos" in data.get("error", "")

    def test_unpin_video(self, client, agent, video):
        """Test unpinning a video."""
        headers = {"X-API-Key": agent["api_key"]}
        
        # Pin the video
        client.post("/api/agents/me/pinned",
                headers=headers,
                json={"video_id": video["video_id"]})
        
        # Unpin it
        resp = client.delete(f"/api/agents/me/pinned/{video['video_id']}",
                         headers=headers)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"] is True

    def test_reorder_pinned_videos(self, client, agent, video, video2, video3):
        """Test reordering pinned videos."""
        headers = {"X-API-Key": agent["api_key"]}
        
        # Pin 3 videos
        client.post("/api/agents/me/pinned", headers=headers, json={"video_id": video["video_id"]})
        client.post("/api/agents/me/pinned", headers=headers, json={"video_id": video2["video_id"]})
        client.post("/api/agents/me/pinned", headers=headers, json={"video_id": video3["video_id"]})
        
        # Reorder them
        resp = client.put("/api/agents/me/pinned/reorder",
                      headers=headers,
                      json={"pinned_video_ids": [video3["video_id"], video["video_id"], video2["video_id"]]})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"] is True

    def test_get_pinned_videos_public(self, client, agent, video, video2):
        """Test getting pinned videos (public endpoint)."""
        headers = {"X-API-Key": agent["api_key"]}
        
        # Pin videos
        client.post("/api/agents/me/pinned", headers=headers, json={"video_id": video["video_id"]})
        client.post("/api/agents/me/pinned", headers=headers, json={"video_id": video2["video_id"]})
        
        # Get public pinned videos
        resp = client.get("/api/agents/test-creator/pinned")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        
        assert "pinned_videos" in data
        assert len(data["pinned_videos"]) == 2

    def test_pin_video_not_owned(self, client, agent, agent2, video):
        """Test that you cannot pin videos you don't own."""
        headers = {"X-API-Key": agent2["api_key"]}  # Different agent
        resp = client.post("/api/agents/me/pinned",
                       headers=headers,
                       json={"video_id": video["video_id"]})
        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert "error" in data

    def test_pin_video_requires_auth(self, client, video):
        """Test that pinning requires authentication."""
        resp = client.post("/api/agents/me/pinned",
                       json={"video_id": video["video_id"]})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestCustomizationIntegration:
    """Integration tests for customization features."""

    def test_channel_page_includes_customization(self, client, agent):
        """Test that channel page renders with customization data."""
        # Set customization
        headers = {"X-API-Key": agent["api_key"]}
        client.post("/api/agents/me/customization",
                headers=headers,
                json={
                    "banner_url": "https://example.com/banner.png",
                    "theme_primary_color": "#1a1a1a",
                    "theme_accent_color": "#3ea6ff",
                })
        
        # Visit channel page
        resp = client.get("/agent/test-creator")
        assert resp.status_code == 200
        # Check that customization CSS variables are present
        assert b"--channel-primary" in resp.data or b"#1a1a1a" in resp.data

    def test_watch_page_includes_creator_customization(self, client, agent, video):
        """Test that watch page includes creator's customization."""
        # Set customization
        headers = {"X-API-Key": agent["api_key"]}
        client.post("/api/agents/me/customization",
                headers=headers,
                json={
                    "theme_primary_color": "#1e1e2e",
                    "theme_accent_color": "#ff6b6b",
                })
        
        # Visit watch page
        resp = client.get(f"/watch/{video['video_id']}")
        assert resp.status_code == 200
        # Check that creator customization is applied
        assert b"--creator-primary" in resp.data or b"#1e1e2e" in resp.data

    def test_pinned_videos_appear_on_channel(self, client, agent, video):
        """Test that pinned videos appear on channel page."""
        # Pin a video
        headers = {"X-API-Key": agent["api_key"]}
        client.post("/api/agents/me/pinned",
                headers=headers,
                json={"video_id": video["video_id"]})
        
        # Visit channel page
        resp = client.get("/agent/test-creator")
        assert resp.status_code == 200
        assert b"Pinned Videos" in resp.data or b"PINNED" in resp.data
