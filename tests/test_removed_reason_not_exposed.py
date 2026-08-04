# SPDX-License-Identifier: MIT
"""Verify removed_reason is stripped from public responses but visible to owners.

Regression test for #1602 — ``removed_reason`` is internal moderation metadata
(spam, policy violation, etc.) that was leaking into public API responses.
Owners need to see it so they know why their content was pulled; everyone
else must not.
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

os.environ.setdefault("BOTTUBE_BASE_DIR", "/tmp/bottube_test_removed_reason")
os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_removed_reason/bottube.db")

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
    db_path = tmp_path / "bottube_removed_reason.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server._ctr_tracker = None
    bottube_server._ab_manager = None
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _seed_agent_and_video(db, *, reason="spam"):
    """Insert one agent with a removed video carrying a removed_reason."""
    cur = db.execute(
        """
        INSERT INTO agents
            (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
        VALUES (?, ?, ?, '', '', '', 0, ?, ?)
        """,
        ("reason_test_bot", "Reason Test Bot", "bottube_sk_reason", time.time(), time.time()),
    )
    agent_id = int(cur.lastrowid)

    db.execute(
        """
        INSERT INTO videos
            (video_id, agent_id, title, filename, created_at, is_removed, removed_reason)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        ("removedVid001", agent_id, "Pulled video", "removedVid001.mp4", time.time(), reason),
    )
    # active video for comparison
    db.execute(
        """
        INSERT INTO videos
            (video_id, agent_id, title, filename, created_at, is_removed)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        ("activeVid0001", agent_id, "Active video", "activeVid0001.mp4", time.time()),
    )
    db.commit()
    return agent_id


def test_public_profile_hides_removed_videos(client):
    """Visitor must not see removed videos at all on the owner profile."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        _seed_agent_and_video(db)

    resp = client.get("/api/agents/reason_test_bot")
    assert resp.status_code == 200
    data = resp.get_json()
    vids = {v["video_id"]: v for v in data["videos"]}
    assert "activeVid0001" in vids
    assert "removedVid001" not in vids  # removed video hidden from public
    # active video must not carry removed_reason
    assert "removed_reason" not in vids["activeVid0001"]


def test_owner_sees_removed_reason(client):
    """Logged-in owner sees their removed video and the reason for removal."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        agent_id = _seed_agent_and_video(db)

    with client.session_transaction() as sess:
        sess["user_id"] = agent_id

    resp = client.get("/api/agents/reason_test_bot")
    assert resp.status_code == 200
    data = resp.get_json()
    vids = {v["video_id"]: v for v in data["videos"]}
    assert "removedVid001" in vids  # owner can see removed video
    assert vids["removedVid001"]["removed_reason"] == "spam"
    # active video does not carry removed_reason even for owner
    assert vids["activeVid0001"].get("removed_reason", "") == ""


def test_public_video_list_hides_removed_reason(client):
    """The public /api/videos list must never expose removed_reason."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        _seed_agent_and_video(db)

    resp = client.get("/api/videos")
    assert resp.status_code == 200
    data = resp.get_json()
    for v in data["videos"]:
        assert "removed_reason" not in v, f"removed_reason leaked in list: {v}"
