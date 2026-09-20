# SPDX-License-Identifier: MIT
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tempfile

TEST_BASE_DIR = tempfile.mkdtemp(prefix="bottube_test_public_comments_")
os.environ.setdefault("BOTTUBE_BASE_DIR", TEST_BASE_DIR)
os.environ.setdefault("BOTTUBE_DB_PATH", f"{TEST_BASE_DIR}/bottube.db")

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
    db_path = tmp_path / "bottube_public_comments_banned_authors.db"

    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server._ctr_tracker = None
    bottube_server._ab_manager = None
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, *, is_banned: int = 0) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio,
                 avatar_url, is_human, is_banned, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', 0, ?, ?, ?)
            """,
            (
                agent_name,
                agent_name.title(),
                f"bottube_sk_{agent_name}",
                is_banned,
                time.time(),
                time.time(),
            ),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(
    video_id: str,
    agent_id: int,
    *,
    is_removed: int = 0,
) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                agent_id,
                f"Video {video_id}",
                f"{video_id}.mp4",
                time.time(),
                is_removed,
            ),
        )
        db.commit()


def _insert_comment(
    video_id: str,
    agent_id: int,
    content: str,
    ts: float = None,
) -> None:
    if ts is None:
        ts = time.time()
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, agent_id, content, ts),
        )
        db.commit()


def test_video_comments_api_filters_banned_authors(client):
    owner_id = _insert_agent("vid_owner_1881")
    active_user_id = _insert_agent("active_user_1881")
    banned_user_id = _insert_agent("banned_user_1881", is_banned=1)

    _insert_video("vid_1881_comments", owner_id)
    _insert_comment("vid_1881_comments", active_user_1881_comment := active_user_id, "Hello from active user")
    _insert_comment("vid_1881_comments", banned_user_id, "Hello from banned user")

    resp = client.get("/api/videos/vid_1881_comments/comments")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "comments" in data
    assert data["count"] == 1
    authors = [c["agent_name"] for c in data["comments"]]
    assert authors == ["active_user_1881"]


def test_video_describe_api_filters_banned_authors(client):
    owner_id = _insert_agent("describe_owner_1881")
    active_user_id = _insert_agent("describe_active_1881")
    banned_user_id = _insert_agent("describe_banned_1881", is_banned=1)

    _insert_video("vid_1881_describe", owner_id)
    _insert_comment("vid_1881_describe", active_user_id, "Active describe comment")
    _insert_comment("vid_1881_describe", banned_user_id, "Banned describe comment")

    resp = client.get("/api/videos/vid_1881_describe/describe")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "comments" in data
    assert data["comment_count"] == 1
    authors = [c["agent"] for c in data["comments"]]
    assert authors == ["describe_active_1881"]


def test_browser_watch_page_filters_banned_authors(client, monkeypatch):
    owner_id = _insert_agent("watch_owner_1881")
    active_user_id = _insert_agent("watch_active_1881")
    banned_user_id = _insert_agent("watch_banned_1881", is_banned=1)

    _insert_video("vid_1881_watch", owner_id)
    _insert_comment("vid_1881_watch", active_user_id, "Active watch comment")
    _insert_comment("vid_1881_watch", banned_user_id, "Banned watch comment")

    context_captured = {}

    def mock_render_template(template_name, **context):
        context_captured.update(context)
        return "<html>watch page</html>"

    monkeypatch.setattr(bottube_server, "render_template", mock_render_template)

    resp = client.get("/watch/vid_1881_watch")
    assert resp.status_code == 200
    assert "comments" in context_captured
    authors = [c["agent_name"] for c in context_captured["comments"]]
    assert authors == ["watch_active_1881"]


def test_recent_comments_feed_returns_only_public_active_context(client):
    active_owner_id = _insert_agent("recent_active_owner_1881")
    banned_owner_id = _insert_agent("recent_banned_owner_1881", is_banned=1)
    active_commenter_id = _insert_agent("recent_active_commenter_1881")
    banned_commenter_id = _insert_agent("recent_banned_commenter_1881", is_banned=1)

    # 1. Public video owned by active owner
    _insert_video("public_vid_1", active_owner_id)
    _insert_comment("public_vid_1", active_commenter_id, "Valid comment on public video", ts=100.0)
    _insert_comment("public_vid_1", banned_commenter_id, "Banned comment on public video", ts=101.0)

    # 2. Removed video owned by active owner
    _insert_video("removed_vid_1", active_owner_id, is_removed=1)
    _insert_comment("removed_vid_1", active_commenter_id, "Comment on removed video", ts=102.0)

    # 3. Video owned by banned owner
    _insert_video("banned_owner_vid_1", banned_owner_id)
    _insert_comment("banned_owner_vid_1", active_commenter_id, "Comment on video of banned owner", ts=103.0)

    resp = client.get("/api/comments/recent?since=0&limit=50")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "comments" in data
    
    # Only 1 comment should pass: active commenter on public video owned by active owner
    items = data["comments"]
    assert len(items) == 1
    assert items[0]["video_id"] == "public_vid_1"
    assert items[0]["agent_name"] == "recent_active_commenter_1881"
    assert items[0]["content"] == "Valid comment on public video"


def test_comments_api_returns_404_for_nonpublic_video(client):
    banned_owner_id = _insert_agent("nonpublic_owner_1881", is_banned=1)
    _insert_video("banned_video_1881", banned_owner_id)

    resp = client.get("/api/videos/banned_video_1881/comments")
    assert resp.status_code == 404
