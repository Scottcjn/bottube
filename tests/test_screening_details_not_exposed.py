# SPDX-License-Identifier: MIT
"""Verify screening_details and removed_reason are stripped from public API responses.

Regression test for #1587 — the /api/videos endpoint returned the raw
screening_details column, leaking internal infra info (proxy timeouts,
vision model status, tier thresholds).
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

os.environ.setdefault("BOTTUBE_BASE_DIR", "/tmp/bottube_test_screening")
os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_screening/bottube.db")

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
    db_path = tmp_path / "bottube_screening.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_video(video_id: str, screening_details: str, removed_reason: str = "") -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', 0, ?, ?)
            """,
            ("screening_test_bot", "Screening Test Bot", "bottube_sk_screening", time.time(), time.time()),
        )
        agent_id = int(cur.lastrowid)
        cur = db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed,
                 screening_status, screening_details, removed_reason)
            VALUES (?, ?, ?, ?, ?, 0, 'manual_review', ?, ?)
            """,
            (video_id, agent_id, "Test", f"{video_id}.mp4", time.time(), screening_details, removed_reason),
        )
        db.commit()
        return int(cur.lastrowid)


_SENSITIVE = '{"status":"manual_review","tier2":{"error":"Connection refused","proxy_error":"timed out"}}'


def test_list_strips_screening_details(client):
    """screening_details must not appear in /api/videos list response."""
    _insert_video("screen_test_01", _SENSITIVE, removed_reason="spam_check_failed")

    resp = client.get("/api/videos")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] >= 1
    for v in data["videos"]:
        assert "screening_details" not in v, "screening_details leaked in list response"
        assert "removed_reason" not in v, "removed_reason leaked in list response"


def test_single_video_strips_screening_details(client):
    """screening_details must not appear in GET /api/videos/<id>."""
    _insert_video("screen_single_01", _SENSITIVE, removed_reason="")

    resp = client.get("/api/videos/screen_single_01")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "screening_details" not in data
    assert "removed_reason" not in data
