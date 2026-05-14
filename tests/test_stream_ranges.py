import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_stream_ranges_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_stream_ranges_bootstrap.db")
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
    db_path = tmp_path / "bottube_stream_ranges.db"
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    monkeypatch.setenv("BOTTUBE_DB", str(db_path))
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "VIDEO_DIR", video_dir, raising=False)
    bottube_server.app.config["TESTING"] = True
    bottube_server.init_db()
    yield bottube_server.app.test_client()


def _insert_stream_video(video_id="stream_range_vid", content=b"abcdefghij"):
    filename = f"{video_id}.mp4"
    (bottube_server.VIDEO_DIR / filename).write_bytes(content)
    with sqlite3.connect(str(bottube_server.DB_PATH)) as conn:
        cur = conn.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', 1, 1)
            """,
            ("streamer", "Streamer", "bottube_sk_streamer"),
        )
        conn.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, 1, 0)
            """,
            (video_id, cur.lastrowid, "Stream range video", filename),
        )
        conn.commit()
    return video_id, len(content)


def test_stream_video_serves_valid_byte_range(client):
    video_id, size = _insert_stream_video()

    response = client.get(
        f"/api/videos/{video_id}/stream",
        headers={"Range": "bytes=0-1"},
    )

    assert response.status_code == 206
    assert response.headers["Content-Range"] == f"bytes 0-1/{size}"
    assert response.headers["Content-Length"] == "2"
    assert response.get_data() == b"ab"


def test_stream_video_rejects_malformed_range_header(client):
    video_id, _ = _insert_stream_video()

    response = client.get(
        f"/api/videos/{video_id}/stream",
        headers={"Range": "bytes=abc-def"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "invalid range"}


def test_stream_video_rejects_unsatisfiable_range(client):
    video_id, size = _insert_stream_video()

    response = client.get(
        f"/api/videos/{video_id}/stream",
        headers={"Range": "bytes=999999999-"},
    )

    assert response.status_code == 416
    assert response.headers["Content-Range"] == f"bytes */{size}"
    assert response.get_json() == {"ok": False, "error": "range not satisfiable"}
