import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_BASE_DIR = "/tmp/bottube_test_public_analytics_visibility"
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
    db_path = tmp_path / "bottube_public_analytics_visibility.db"

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
                agent_name.replace("_", " ").title(),
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
    title: str,
    views: int = 0,
    likes: int = 0,
    is_removed: int = 0,
) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, description, filename, tags,
                 category, created_at, is_removed, views, likes)
            VALUES (?, ?, ?, ?, ?, '[]', 'other', ?, ?, ?, ?)
            """,
            (
                video_id,
                agent_id,
                title,
                f"{title} description",
                f"{video_id}.mp4",
                time.time(),
                is_removed,
                views,
                likes,
            ),
        )
        db.commit()


def _insert_view(video_id: str, *, created_at: float | None = None) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO views (video_id, ip_address, created_at)
            VALUES (?, '127.0.0.1', ?)
            """,
            (video_id, created_at or time.time()),
        )
        db.commit()


def _insert_comment(video_id: str, agent_id: int) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, created_at)
            VALUES (?, ?, 'analytics fixture comment', ?)
            """,
            (video_id, agent_id, time.time()),
        )
        db.commit()


def test_agent_analytics_hides_banned_agents(client):
    banned_agent = _insert_agent("banned_agent", is_banned=1)
    _insert_video("banned-clip", banned_agent, title="Banned Clip", views=12)

    resp = client.get("/api/agents/banned_agent/analytics")

    assert resp.status_code == 404


def test_agent_analytics_excludes_removed_video_events(client):
    agent_id = _insert_agent("visible_agent")
    commenter_id = _insert_agent("commenter_agent")
    _insert_video("visible-clip", agent_id, title="Visible Clip", views=1)
    _insert_video(
        "removed-clip",
        agent_id,
        title="Removed Clip",
        views=99,
        is_removed=1,
    )
    _insert_view("visible-clip")
    _insert_view("removed-clip")
    _insert_comment("visible-clip", commenter_id)
    _insert_comment("removed-clip", commenter_id)

    resp = client.get("/api/agents/visible_agent/analytics?days=30")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["totals"]["videos"] == 1
    assert data["totals"]["views"] == 1
    assert data["comments_in_period"] == 1
    assert sum(row["views"] for row in data["daily_views"]) == 1
    assert [
        video["video_id"] for video in data["top_videos"]
    ] == ["visible-clip"]


def test_video_analytics_hides_banned_agent_videos(client):
    banned_agent = _insert_agent("banned_agent", is_banned=1)
    _insert_video("banned-clip", banned_agent, title="Banned Clip", views=12)

    resp = client.get("/api/videos/banned-clip/analytics")

    assert resp.status_code == 404


def test_video_analytics_still_returns_visible_videos(client):
    agent_id = _insert_agent("visible_agent")
    _insert_video("visible-clip", agent_id, title="Visible Clip", views=3)
    _insert_view("visible-clip")

    resp = client.get("/api/videos/visible-clip/analytics")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["video_id"] == "visible-clip"
    assert data["totals"]["views"] == 3
    assert sum(row["views"] for row in data["daily_views"]) == 1
