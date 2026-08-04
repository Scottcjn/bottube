"""Test that removed_reason is not exposed in public API responses (#1587)."""

import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bottube_server


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Create test client with temporary database."""
    db_path = tmp_path / "bottube_removed_reason_test.db"
    video_dir = tmp_path / "videos"
    video_dir.mkdir()

    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "VIDEO_DIR", video_dir, raising=False)
    monkeypatch.setattr(
        bottube_server,
        "render_template",
        lambda *args, **kwargs: "rendered",
    )
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True

    # Create test data
    with bottube_server.app.app_context():
        db = bottube_server.get_db()

        # Create test agent
        cur = db.execute(
            """INSERT INTO agents (agent_name, display_name, avatar_url, api_key, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("test_agent", "Test Agent", "https://example.com/avatar.jpg", "test_api_key_12345", time.time())
        )
        agent_id = cur.lastrowid

        # Create an active video
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, description, is_removed, removed_reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("active_vid", agent_id, "Active Video", "This is active", 0, None, time.time())
        )

        # Create a removed video (only owner should see removed_reason)
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, description, is_removed, removed_reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("removed_vid", agent_id, "Removed Video", "This was removed", 1, "policy_violation", time.time())
        )

        db.commit()

    yield bottube_server.app.test_client()


def test_public_profile_hides_removed_videos_and_reason(client):
    """Public visitor should not see removed videos or their reasons."""
    resp = client.get("/api/agents/test_agent")
    assert resp.status_code == 200
    data = resp.get_json()

    # Only active video should be in response
    assert data["video_count"] == 1
    assert len(data["videos"]) == 1
    assert data["videos"][0]["video_id"] == "active_vid"

    # No removed_reason in any video
    for video in data["videos"]:
        assert "removed_reason" not in video


def test_owner_sees_removed_video_with_reason(client):
    """Agent owner should see their removed videos with the removal reason."""
    # This test uses app context to set the logged-in user
    # In a real scenario, this would be done through authentication
    with app.test_client() as test_client:
        db = get_db()
        agent = db.execute("SELECT id FROM agents WHERE agent_name = ?", ("test_agent",)).fetchone()

        # Simulate owner login by setting g.user
        with test_client:
            # Make request and check within request context
            with app.test_request_context("/api/agents/test_agent"):
                from flask import g
                g.user = {"id": agent["id"]}

                resp = test_client.get("/api/agents/test_agent")
                assert resp.status_code == 200
                data = resp.get_json()

                # Owner should see both active and removed videos
                assert data["video_count"] == 2
                assert len(data["videos"]) == 2

                # Check that removed video includes the reason
                removed_video = next((v for v in data["videos"] if v["video_id"] == "removed_vid"), None)
                assert removed_video is not None
                assert removed_video.get("removed_reason") == "policy_violation"


def test_api_videos_list_never_exposes_removed_reason(client):
    """The /api/videos list endpoint should never expose removed_reason, even for internal calls."""
    resp = client.get("/api/videos")
    assert resp.status_code == 200
    data = resp.get_json()

    # Check all videos in response
    for video in data.get("videos", []):
        assert "removed_reason" not in video, "removed_reason should never be in /api/videos response"
