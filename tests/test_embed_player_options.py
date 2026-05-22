import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_embed_player.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_embed_player.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import bottube_server  # noqa: E402

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_embed_player.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_video(video_id="embedOpts01"):
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio,
                 avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?)
            """,
            ("embed-agent", "Embed Agent", "test-embed-api-key", 1.0, 1.0),
        )
        agent_id = int(cur.lastrowid)
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (video_id, agent_id, "Embed Player Test", f"{video_id}.mp4", 1.0),
        )
        db.commit()
    return video_id


def test_embed_player_applies_url_options_and_copy_button(client):
    video_id = _insert_video()

    response = client.get(f"/embed/{video_id}?autoplay=1&loop=1&mute=1")

    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "ALLOWALL"
    html = response.get_data(as_text=True)
    assert "<video controls autoplay loop muted playsinline>" in html
    assert 'onclick="copyEmbed(this)"' in html
    assert "Copy embed" in html
    assert f"https://bottube.ai/embed/{video_id}" in html
    assert 'frameborder=\\"0\\" allowfullscreen' in html


def test_embed_player_leaves_options_off_by_default(client):
    video_id = _insert_video("embedOpts02")

    response = client.get(f"/embed/{video_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<video controls playsinline>" in html
    assert "autoplay loop muted" not in html
