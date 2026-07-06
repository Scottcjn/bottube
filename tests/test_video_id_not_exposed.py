# SPDX-License-Identifier: MIT
"""Verify that the internal integer row id is not exposed in video API responses.

Regression test for #1564 — the list endpoint returned an ``id`` field (the SQLite
auto-increment rowid) alongside ``video_id``. Clients used ``id`` to build
``/api/videos/<id>`` URLs, which 404 because routes expect the text ``video_id``.
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_BASE_DIR", "/tmp/bottube_test_id_exposed")
os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_id_exposed/bottube.db")

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
    db_path = tmp_path / "bottube_id_exposed.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server._ctr_tracker = None
    bottube_server._ab_manager = None
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent() -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', 0, ?, ?)
            """,
            ("id_test_bot", "ID Test Bot", "bottube_sk_idtest", time.time(), time.time()),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(video_id: str) -> int:
    agent_id = _insert_agent()
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, "Test video", f"{video_id}.mp4", time.time()),
        )
        db.commit()
        return int(cur.lastrowid)


def test_list_does_not_expose_internal_id(client):
    """The /api/videos list must not return the integer ``id`` field."""
    public_video_id = "abc123XYZqw"
    internal_id = _insert_video(public_video_id)
    assert internal_id != public_video_id  # sanity check

    resp = client.get("/api/videos")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] >= 1

    for v in data["videos"]:
        assert "id" not in v, f"Internal rowid leaked in list response: {v}"
        assert "video_id" in v


def test_single_video_does_not_expose_internal_id(client):
    """GET /api/videos/<video_id> must not include ``id``."""
    public_video_id = "singleVidId01"
    _insert_video(public_video_id)

    resp = client.get(f"/api/videos/{public_video_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "id" not in data, f"Internal rowid leaked in single-video response: {data}"
    assert data["video_id"] == public_video_id
