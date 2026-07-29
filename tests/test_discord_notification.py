# SPDX-License-Identifier: MIT
"""Tests for Discord notification — fire_discord_notification."""

import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# Bootstrap the environment before any bottube_server imports fire
# (init_gemini_tables and other module-level code need a writable DB path)
_tmp = tempfile.mkdtemp()
os.environ.setdefault("BOTTUBE_BASE_DIR", _tmp)
os.environ.setdefault("BOTTUBE_DB", os.path.join(_tmp, "bottube.db"))

# Ensure the bootstrap DB exists
Path(_tmp).mkdir(parents=True, exist_ok=True)
Path(os.environ["BOTTUBE_DB"]).touch()

# Patch sqlite3.connect so that the hard-coded /root/bottube/bottube.db
# fallback in init_gemini_tables redirects to our temp DB
_orig_connect = sqlite3.connect


def _bootstrap_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB"]
    return _orig_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_connect

# Now import — module-level init_gemini_tables() will use the redirected path
from bottube_server import DB_PATH, fire_discord_notification, init_db

# Restore original connect
sqlite3.connect = _orig_connect


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_db():
    """Create a fresh test database for each test."""
    db_path = Path(tempfile.mkdtemp()) / "test.db"
    # Patch DB_PATH before init_db runs
    import bottube_server
    original_db = bottube_server.DB_PATH
    bottube_server.DB_PATH = db_path
    init_db()
    yield db_path
    bottube_server.DB_PATH = original_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_sync(self):
    """Run a daemon thread's target synchronously (inline)."""
    self._target()


def _insert_agent(db_path, agent_id: int, webhook_url: str):
    """Insert a minimal agent row with the given discord_webhook_url."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO agents (id, agent_name, api_key, created_at, discord_webhook_url) "
        "VALUES (?, ?, ?, ?, ?)",
        (agent_id, f"test_agent_{agent_id}", f"key_{agent_id}", time.time(), webhook_url),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDiscordNotification:
    """Send-path tests for fire_discord_notification."""

    def test_sends_to_discord_webhook(self, test_db):
        """With a valid discord.com webhook URL, POST to the webhook endpoint."""
        _insert_agent(test_db, 1, "https://discord.com/api/webhooks/12345/test")

        with patch("bottube_server.urllib.request.urlopen") as mock_urlopen, \
             patch.object(threading.Thread, "start", _run_sync):

            fire_discord_notification(
                agent_id=1,
                notif_type="new_video",
                message="Test notification",
                from_agent="test_agent",
                video_id="abc123",
                video_title="Test Video",
            )

            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]

            # Assert the URL is a discord.com webhook URL
            url = req.get_full_url()
            assert "discord.com" in url
            assert "/api/webhooks/" in url

            # Assert the payload is well-formed
            body = req.data
            payload = json.loads(body)
            assert payload["username"] == "BoTTube"
            assert len(payload["embeds"]) == 1

            embed = payload["embeds"][0]
            assert embed["title"] == "BoTTube Notification"
            assert embed["description"] == "Test notification"
            assert embed["author"]["name"] == "test_agent"
            assert embed["url"] == "https://bottube.ai/watch/abc123"
            assert embed["fields"][0]["value"] == "Test Video"

            # Assert correct method
            assert req.method == "POST"

    def test_invalid_webhook_skips_silently(self, test_db):
        """A non-discord.com webhook URL should silently skip without POSTing."""
        _insert_agent(test_db, 2, "https://evil.com/hook")

        with patch("bottube_server.urllib.request.urlopen") as mock_urlopen, \
             patch.object(threading.Thread, "start", _run_sync):

            fire_discord_notification(
                agent_id=2,
                notif_type="new_video",
                message="Should not send",
            )
            mock_urlopen.assert_not_called()

    def test_empty_webhook_skips_silently(self, test_db):
        """An empty webhook URL should silently skip without POSTing."""
        _insert_agent(test_db, 3, "")

        with patch("bottube_server.urllib.request.urlopen") as mock_urlopen, \
             patch.object(threading.Thread, "start", _run_sync):

            fire_discord_notification(
                agent_id=3,
                notif_type="new_video",
                message="Should not send",
            )
            mock_urlopen.assert_not_called()

    def test_no_agent_row_skips_silently(self, test_db):
        """A non-existent agent ID should silently skip without POSTing."""
        with patch("bottube_server.urllib.request.urlopen") as mock_urlopen, \
             patch.object(threading.Thread, "start", _run_sync):

            fire_discord_notification(
                agent_id=999,
                notif_type="new_video",
                message="Should not send",
            )
            mock_urlopen.assert_not_called()

    def test_sends_minimal_payload(self, test_db):
        """Without optional fields (video_id, from_agent, video_title), send a minimal embed."""
        _insert_agent(test_db, 4, "https://discord.com/api/webhooks/99999/abc")

        with patch("bottube_server.urllib.request.urlopen") as mock_urlopen, \
             patch.object(threading.Thread, "start", _run_sync):

            fire_discord_notification(
                agent_id=4,
                notif_type="new_video",
                message="Simple notification",
            )

            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data)

            embed = payload["embeds"][0]
            assert embed["title"] == "BoTTube Notification"
            assert embed["description"] == "Simple notification"
            # Optional fields should be absent
            assert "url" not in embed
            assert "fields" not in embed
            assert "author" not in embed