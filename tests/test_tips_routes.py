import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_tips_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_tips_bootstrap.db")
os.environ.setdefault("BOTTUBE_BASE_DIR", "/tmp")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_tips_routes.db"
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    monkeypatch.setenv("BOTTUBE_DB", str(db_path))
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server.app.config["TESTING"] = True
    bottube_server.init_db()
    yield bottube_server.app.test_client()


def _insert_agent_and_video(video_id="video_tips_1"):
    with sqlite3.connect(str(bottube_server.DB_PATH)) as conn:
        now = time.time()
        cur = conn.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', ?, ?)
            """,
            ("creator", "Creator", "bottube_sk_creator", now, now),
        )
        agent_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, "Tips video", "tips.mp4", now),
        )
        conn.commit()
    return video_id


def test_video_tips_returns_404_for_missing_video(client):
    response = client.get("/api/videos/no_such_video_codex_1102/tips")

    assert response.status_code == 404
    assert response.get_json() == {"ok": False, "error": "video not found"}


def test_video_tips_preserves_empty_totals_for_existing_video(client):
    video_id = _insert_agent_and_video()

    response = client.get(f"/api/videos/{video_id}/tips")

    assert response.status_code == 200
    data = response.get_json()
    assert data["video_id"] == video_id
    assert data["tips"] == []
    assert data["total_tips"] == 0
    assert data["total_amount"] == 0
    assert data["pending_tips"] == 0
    assert data["pending_amount"] == 0
