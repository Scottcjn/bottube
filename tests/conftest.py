# SPDX-License-Identifier: MIT
"""
Shared pytest fixtures for BoTTube tests.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def app():
    """Create a test Flask app with an in-memory database."""
    # We need to set up the environment before importing bottube_server
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

        # Bootstrap database schema by running the init from the server
        # Ensure fresh import
        for mod_name in list(sys.modules.keys()):
            if "bottube_server" in mod_name:
                del sys.modules[mod_name]
            if "paypal_packages" in mod_name:
                del sys.modules[mod_name]
            if "gpu_marketplace" in mod_name:
                del sys.modules[mod_name]
            if "banano_blueprint" in mod_name:
                del sys.modules[mod_name]
            if "captions_blueprint" in mod_name:
                del sys.modules[mod_name]

        sys.path.insert(0, str(server_path))
        
        # Set DB path before importing
        import bottube_server
        bottube_server.DB_PATH = db_path
        bottube_server.VIDEO_DIR = video_dir
        bottube_server.THUMB_DIR = thumb_dir
        bottube_server.AVATAR_DIR = avatar_dir

        flask_app = bottube_server.app
        flask_app.config["TESTING"] = True
        flask_app.config["SECRET_KEY"] = "test-secret-key"
        # Use the templates from the project
        flask_app.template_folder = str(server_path / "bottube_templates")

        with flask_app.app_context():
            bottube_server.init_db()

        yield flask_app


@pytest.fixture
def client(app):
    """Return a Flask test client."""
    return app.test_client()


@pytest.fixture
def registered_agent(client):
    """Register a test agent and return dict with agent_name and api_key."""
    resp = client.post("/api/register", json={
        "agent_name": "test_discoverability_bot",
        "display_name": "Discoverability Test Bot",
        "bio": "A bot for testing discoverability features",
    })
    data = resp.get_json()
    assert resp.status_code == 201, f"Registration failed: {data}"
    return {"agent_name": data["agent_name"], "api_key": data["api_key"]}
