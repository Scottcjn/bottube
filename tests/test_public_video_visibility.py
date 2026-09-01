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

TEST_BASE_DIR = "/tmp/bottube_test_public_video_visibility"
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
    db_path = tmp_path / "bottube_public_video_visibility.db"
    video_dir = tmp_path / "videos"
    video_dir.mkdir()

    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "VIDEO_DIR", video_dir, raising=False)
    monkeypatch.setattr(
        bottube_server,
        "render_template",
        lambda *args, **kwargs: "rendered",
    )
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server._ctr_tracker = None
    bottube_server._ab_manager = None
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, *, is_banned: int = 0, is_human: int = 0) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio,
                 avatar_url, is_human, is_banned, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?, ?, ?)
            """,
            (
                agent_name,
                agent_name.replace("_", " ").title(),
                f"bottube_sk_{agent_name}",
                is_human,
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
    views: int = 0,
    likes: int = 0,
) -> None:
    video_file = bottube_server.VIDEO_DIR / f"{video_id}.mp4"
    video_file.write_bytes(b"fake video bytes")
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, description, filename, tags,
                 category, created_at, is_removed, views, likes, width, height)
            VALUES (?, ?, ?, ?, ?, '[]', 'other', ?, ?, ?, ?, 640, 360)
            """,
            (
                video_id,
                agent_id,
                f"{video_id} title",
                "moderation visibility fixture",
                f"{video_id}.mp4",
                time.time(),
                is_removed,
                views,
                likes,
            ),
        )
        db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, created_at)
            VALUES (?, ?, 'hidden context', ?)
            """,
            (video_id, agent_id, time.time()),
        )
        db.commit()


def test_public_routes_hide_removed_videos(client):
    agent_id = _insert_agent("visible_agent")
    _insert_video("removed-clip", agent_id, is_removed=1)

    hidden_paths = [
        "/api/videos/removed-clip",
        "/api/videos/removed-clip/view",
        "/api/videos/removed-clip/describe",
        "/api/videos/removed-clip/comments",
        "/api/videos/removed-clip/related",
        "/api/videos/removed-clip/stream",
        "/watch/removed-clip",
        "/embed/removed-clip",
        "/oembed?url=https://bottube.ai/watch/removed-clip",
    ]

    for path in hidden_paths:
        assert client.get(path).status_code == 404, path


def test_public_routes_hide_videos_from_banned_agents(client):
    agent_id = _insert_agent("banned_agent", is_banned=1)
    _insert_video("banned-clip", agent_id)

    hidden_paths = [
        "/api/videos/banned-clip",
        "/api/videos/banned-clip/view",
        "/api/videos/banned-clip/describe",
        "/api/videos/banned-clip/comments",
        "/api/videos/banned-clip/related",
        "/api/videos/banned-clip/stream",
        "/watch/banned-clip",
        "/embed/banned-clip",
        "/oembed?url=https://bottube.ai/watch/banned-clip",
    ]

    for path in hidden_paths:
        assert client.get(path).status_code == 404, path


def test_public_routes_still_return_visible_videos(client):
    agent_id = _insert_agent("visible_agent")
    _insert_video("visible-clip", agent_id)

    expected_ok_paths = [
        "/api/videos/visible-clip",
        "/api/videos/visible-clip/view",
        "/api/videos/visible-clip/describe",
        "/api/videos/visible-clip/comments",
        "/api/videos/visible-clip/related",
        "/api/videos/visible-clip/stream",
        "/watch/visible-clip",
        "/embed/visible-clip",
        "/oembed?url=https://bottube.ai/watch/visible-clip",
    ]

    for path in expected_ok_paths:
        assert client.get(path).status_code == 200, path


def test_public_stats_use_the_same_visibility_denominator(client):
    visible_bot = _insert_agent("stats_visible_bot")
    visible_human = _insert_agent("stats_visible_human", is_human=1)
    banned_bot = _insert_agent("stats_banned_bot", is_banned=1)
    _insert_video("stats-bot-public", visible_bot, views=10, likes=2)
    _insert_video(
        "stats-bot-removed", visible_bot, is_removed=1, views=100, likes=20
    )
    _insert_video("stats-human-public", visible_human, views=5, likes=1)
    _insert_video("stats-banned-public", banned_bot, views=200, likes=30)

    response = client.get("/api/stats?limit=10")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["videos"] == 2
    assert payload["agents"] == 1
    assert payload["humans"] == 1
    assert payload["total_views"] == 15
    assert payload["total_likes"] == 3
    assert payload["total_comments"] == 2
    top_agents = {row["agent_name"]: row for row in payload["top_agents"]}
    assert set(top_agents) == {"stats_visible_bot", "stats_visible_human"}
    assert top_agents["stats_visible_bot"]["video_count"] == 1
    assert top_agents["stats_visible_bot"]["total_views"] == 10
