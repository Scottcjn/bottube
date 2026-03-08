# SPDX-License-Identifier: MIT
"""Tests for the avatar upload endpoint POST /api/agents/me/avatar."""

import io
import time
from unittest.mock import MagicMock, patch

import bottube_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_agent(agent_id=42, agent_name="testbot", display_name="TestBot"):
    """Return a dict-like Row that mimics an sqlite3.Row for an agent."""
    class Row(dict):
        def __getitem__(self, key):
            return super().__getitem__(key)
    return Row(
        id=agent_id,
        agent_name=agent_name,
        display_name=display_name,
        bio="",
        avatar_url="",
        is_banned=0,
        ban_reason="",
        api_key="test-key-abc",
    )


def _mock_get_db(agent=None):
    """Return a mock get_db whose execute handles the API-key lookup."""
    db = MagicMock()

    def _execute(sql, params=()):
        cursor = MagicMock()
        sql_l = sql.lower()
        if "from agents where api_key" in sql_l:
            cursor.fetchone.return_value = agent
        else:
            cursor.fetchone.return_value = None
            cursor.fetchall.return_value = []
        return cursor

    db.execute.side_effect = _execute
    return db


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

def test_avatar_upload_missing_api_key(client):
    """POST without X-API-Key returns 401."""
    resp = client.post("/api/agents/me/avatar")
    assert resp.status_code == 401
    assert "Missing" in resp.get_json()["error"]


def test_avatar_upload_invalid_api_key(client):
    """POST with bad API key returns 401."""
    mock_db = _mock_get_db(agent=None)
    with patch("bottube_server.get_db", return_value=mock_db):
        resp = client.post(
            "/api/agents/me/avatar",
            headers={"X-API-Key": "bad-key"},
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

def test_avatar_upload_invalid_file_type(client):
    """Uploading a non-image file returns 400."""
    agent = _fake_agent()
    mock_db = _mock_get_db(agent=agent)
    with patch("bottube_server.get_db", return_value=mock_db):
        resp = client.post(
            "/api/agents/me/avatar",
            headers={"X-API-Key": "test-key-abc"},
            data={"avatar": (io.BytesIO(b"not-an-image"), "payload.txt")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 400
    assert "Invalid file type" in resp.get_json()["error"]


def test_avatar_upload_file_too_large(client):
    """Uploading a file > MAX_AVATAR_SIZE returns 400."""
    agent = _fake_agent()
    mock_db = _mock_get_db(agent=agent)
    # 6 MB exceeds the 5 MB limit
    big_blob = b"\x00" * (6 * 1024 * 1024)
    with patch("bottube_server.get_db", return_value=mock_db):
        resp = client.post(
            "/api/agents/me/avatar",
            headers={"X-API-Key": "test-key-abc"},
            data={"avatar": (io.BytesIO(big_blob), "huge.png")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 400
    assert "too large" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Rate-limiting test
# ---------------------------------------------------------------------------

def test_avatar_upload_rate_limit(client):
    """Exceeding 5 uploads per hour returns 429."""
    agent = _fake_agent()
    mock_db = _mock_get_db(agent=agent)

    original_rate_limit = bottube_server._rate_limit

    def _selective_rate_limit(key, *args, **kwargs):
        # Only deny the avatar-specific rate limit call
        if key.startswith("avatar:"):
            return False
        return original_rate_limit(key, *args, **kwargs)

    with patch("bottube_server.get_db", return_value=mock_db), \
         patch("bottube_server._rate_limit", side_effect=_selective_rate_limit):
        resp = client.post(
            "/api/agents/me/avatar",
            headers={"X-API-Key": "test-key-abc"},
        )
    assert resp.status_code == 429
    assert "rate" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Successful upload (ffmpeg mocked)
# ---------------------------------------------------------------------------

def test_avatar_upload_with_file_success(client, tmp_path):
    """Uploading a valid PNG calls ffmpeg and returns ok + avatar_url."""
    agent = _fake_agent()
    mock_db = _mock_get_db(agent=agent)
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir()
    out_file = avatar_dir / f"{agent['id']}.jpg"
    out_file.write_bytes(b"\xff\xd8fake-jpeg")

    def fake_run(cmd, **kwargs):
        # Simulate ffmpeg writing the output file (already created above)
        m = MagicMock()
        m.returncode = 0
        m.stderr = b""
        return m

    fake_png = b"\x89PNG" + b"\x00" * 100

    with patch("bottube_server.get_db", return_value=mock_db), \
         patch("bottube_server._rate_limit", return_value=True), \
         patch("bottube_server.AVATAR_DIR", avatar_dir), \
         patch("bottube_server.subprocess.run", side_effect=fake_run):
        resp = client.post(
            "/api/agents/me/avatar",
            headers={"X-API-Key": "test-key-abc"},
            data={"avatar": (io.BytesIO(fake_png), "avatar.png")},
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["avatar_url"] == f"/avatars/{agent['id']}.jpg"


def test_avatar_autogenerate_success(client, tmp_path):
    """POST with no file auto-generates an avatar and returns ok."""
    agent = _fake_agent()
    mock_db = _mock_get_db(agent=agent)
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir()
    out_file = avatar_dir / f"{agent['id']}.jpg"
    out_file.write_bytes(b"\xff\xd8fake-jpeg")

    def fake_run(cmd, **kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stderr = b""
        return m

    with patch("bottube_server.get_db", return_value=mock_db), \
         patch("bottube_server._rate_limit", return_value=True), \
         patch("bottube_server.AVATAR_DIR", avatar_dir), \
         patch("bottube_server.subprocess.run", side_effect=fake_run):
        resp = client.post(
            "/api/agents/me/avatar",
            headers={"X-API-Key": "test-key-abc"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "/avatars/" in data["avatar_url"]


# ---------------------------------------------------------------------------
# MAX_AVATAR_SIZE constant test
# ---------------------------------------------------------------------------

def test_max_avatar_size_is_5mb():
    """MAX_AVATAR_SIZE should be 5 MB to match API documentation."""
    assert bottube_server.MAX_AVATAR_SIZE == 5 * 1024 * 1024
