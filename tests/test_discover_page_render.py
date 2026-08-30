# SPDX-License-Identifier: MIT
"""Regression for #1411: /discover must render when BOTTUBE_BASE_DIR is set."""
import os
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def discover_client(monkeypatch):
    """App with BOTTUBE_BASE_DIR pointing at an empty data dir (no templates)."""
    server_path = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("BOTTUBE_BASE_DIR", tmpdir)
        monkeypatch.setenv("RC_ADMIN_KEY", "0123456789abcdef0123456789abcdef")
        monkeypatch.setenv("RUSTCHAIN_DISABLE_P2P_AUTO_START", "1")

        for mod_name in list(sys.modules):
            if mod_name in {"bottube_server", "search_blueprint"} or mod_name.startswith("bottube_server."):
                sys.modules.pop(mod_name, None)

        sys.path.insert(0, str(server_path))
        import bottube_server

        db_path = Path(tmpdir) / "bottube.db"
        bottube_server.DB_PATH = db_path
        bottube_server.VIDEO_DIR = Path(tmpdir) / "videos"
        bottube_server.THUMB_DIR = Path(tmpdir) / "thumbnails"
        bottube_server.AVATAR_DIR = Path(tmpdir) / "avatars"
        for d in (bottube_server.VIDEO_DIR, bottube_server.THUMB_DIR, bottube_server.AVATAR_DIR):
            d.mkdir(parents=True, exist_ok=True)

        app = bottube_server.app
        app.config["TESTING"] = True
        with app.app_context():
            bottube_server.init_db()

        yield app.test_client()


def test_discover_page_renders_with_external_base_dir(discover_client):
    resp = discover_client.get("/discover/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Discover" in body
    assert "discover-container" in body
