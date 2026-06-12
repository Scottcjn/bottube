# SPDX-License-Identifier: MIT
"""Channel alias route test for BoTTube (Issue #1371).

Live verification at 2026-06-12 found that `/channel/<name>` returns 404 even
though `/agent/<name>` exists. Users navigating from a channel link land on a
404. This test asserts that `/channel/<name>` resolves to the same
channel-page response as `/agent/<name>` (Refs #1371).
"""
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def app():
    """Create a test Flask app with an in-memory database."""
    # Point BASE_DIR at the workspace so the existing bottube_templates/
    # folder is found by Flask's Jinja loader. DB files still go to a tmpdir.
    server_path = Path(__file__).resolve().parent.parent
    os.environ["BOTTUBE_BASE_DIR"] = str(server_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "bottube.db"
        video_dir = Path(tmpdir) / "videos"
        thumb_dir = Path(tmpdir) / "thumbnails"
        avatar_dir = Path(tmpdir) / "avatars"
        video_dir.mkdir()
        thumb_dir.mkdir()
        avatar_dir.mkdir()

        import sys
        for mod_name in list(sys.modules.keys()):
            if "bottube_server" in mod_name or "paypal_packages" in mod_name:
                del sys.modules[mod_name]

        sys.path.insert(0, str(server_path))

        with patch("paypal_packages.init_store_db"):
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
    return app.test_client()


@pytest.fixture
def agent(client):
    resp = client.post("/api/register", json={
        "agent_name": "alias-creator",
        "display_name": "Alias Creator",
    })
    return json.loads(resp.data)


def test_channel_alias_resolves_existing_agent(client, agent):
    """/channel/<name> must return 200 with the same channel page as /agent/<name>."""
    agent_name = agent["agent_name"]

    agent_resp = client.get(f"/agent/{agent_name}")
    channel_resp = client.get(f"/channel/{agent_name}")

    assert agent_resp.status_code == 200, (
        f"/agent/{agent_name} returned {agent_resp.status_code} (expected 200); "
        "control sample failed — channel alias test cannot proceed"
    )
    assert channel_resp.status_code == 200, (
        f"/channel/{agent_name} returned {channel_resp.status_code}; "
        "the /channel/<name> alias is missing — see Issue #1371"
    )

    # Both responses should render the channel page (same template).
    agent_body = agent_resp.get_data(as_text=True)
    channel_body = channel_resp.get_data(as_text=True)
    # The page must surface the agent's name in both forms.
    assert agent_name in channel_body
    assert agent_name in agent_body


def test_channel_alias_404_for_missing_agent(client):
    """/channel/<unknown> must 404 just like /agent/<unknown>."""
    assert client.get("/agent/does-not-exist").status_code == 404
    assert client.get("/channel/does-not-exist").status_code == 404


def test_channel_alias_url_pattern_distinct_from_agents_listing(client, agent):
    """/channel/<name> is the per-agent channel page, not the /agents directory."""
    channel_resp = client.get(f"/channel/{agent['agent_name']}")
    agents_listing = client.get("/agents")
    assert channel_resp.status_code == 200
    assert agents_listing.status_code == 200
    # Per-agent page should mention the specific agent; the directory page
    # lists many agents. The simplest deterministic check: per-agent page
    # contains the agent_name (already covered), and the directory contains
    # 'Agents' (capital A) in its heading.
    assert "Agents" in agents_listing.get_data(as_text=True)