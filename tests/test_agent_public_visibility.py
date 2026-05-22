import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_BASE_DIR = "/tmp/bottube_test_agent_public_visibility"
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
    db_path = tmp_path / "bottube_agent_public_visibility.db"
    rendered = []

    def fake_render_template(template, **context):
        rendered.append((template, context))
        return "rendered"

    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(
        bottube_server,
        "render_template",
        fake_render_template,
    )
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server._ctr_tracker = None
    bottube_server._ab_manager = None
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client(), rendered


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
    is_removed: int = 0,
) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, description, filename, tags,
                 category, created_at, is_removed, views)
            VALUES (?, ?, ?, ?, ?, '[]', 'other', ?, ?, ?)
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
            ),
        )
        db.commit()


def _render_context(rendered, template):
    matches = [context for name, context in rendered if name == template]
    assert matches
    return matches[-1]


def test_agents_page_hides_banned_agents_and_removed_video_counts(client):
    http, rendered = client
    visible_agent = _insert_agent("visible_agent")
    banned_agent = _insert_agent("banned_agent", is_banned=1)
    _insert_video("visible-clip", visible_agent, title="Visible Clip", views=7)
    _insert_video(
        "removed-clip",
        visible_agent,
        title="Removed Clip",
        views=90,
        is_removed=1,
    )
    _insert_video("banned-clip", banned_agent, title="Banned Clip", views=100)

    resp = http.get("/agents")

    assert resp.status_code == 200
    agents = _render_context(rendered, "agents.html")["agents"]
    assert [row["agent_name"] for row in agents] == ["visible_agent"]
    assert agents[0]["video_count"] == 1
    assert agents[0]["total_views"] == 7


def test_agent_profile_api_hides_banned_agents_and_removed_videos(client):
    http, _rendered = client
    visible_agent = _insert_agent("visible_agent")
    banned_agent = _insert_agent("banned_agent", is_banned=1)
    _insert_video("visible-clip", visible_agent, title="Visible Clip")
    _insert_video(
        "removed-clip",
        visible_agent,
        title="Removed Clip",
        is_removed=1,
    )
    _insert_video("banned-clip", banned_agent, title="Banned Clip")

    visible_resp = http.get("/api/agents/visible_agent")
    banned_resp = http.get("/api/agents/banned_agent")

    assert visible_resp.status_code == 200
    payload = visible_resp.get_json()
    assert payload["video_count"] == 1
    assert [
        video["video_id"] for video in payload["videos"]
    ] == ["visible-clip"]
    assert banned_resp.status_code == 404


def test_agent_channel_page_hides_banned_agents_and_removed_videos(client):
    http, rendered = client
    visible_agent = _insert_agent("visible_agent")
    banned_agent = _insert_agent("banned_agent", is_banned=1)
    _insert_video(
        "visible-clip",
        visible_agent,
        title="Visible Clip",
        views=11,
    )
    _insert_video(
        "removed-clip",
        visible_agent,
        title="Removed Clip",
        views=80,
        is_removed=1,
    )
    _insert_video("banned-clip", banned_agent, title="Banned Clip")

    visible_resp = http.get("/agent/visible_agent")
    banned_resp = http.get("/agent/banned_agent")

    assert visible_resp.status_code == 200
    context = _render_context(rendered, "channel.html")
    assert [
        video["video_id"] for video in context["videos"]
    ] == ["visible-clip"]
    assert context["total_views"] == 11
    assert banned_resp.status_code == 404


def test_agent_and_global_rss_hide_banned_agents_and_removed_videos(client):
    http, _rendered = client
    visible_agent = _insert_agent("visible_agent")
    banned_agent = _insert_agent("banned_agent", is_banned=1)
    _insert_video("visible-clip", visible_agent, title="Visible Clip")
    _insert_video(
        "removed-clip",
        visible_agent,
        title="Removed Clip",
        is_removed=1,
    )
    _insert_video("banned-clip", banned_agent, title="Banned Clip")

    agent_rss = http.get("/agent/visible_agent/rss")
    banned_rss = http.get("/agent/banned_agent/rss")
    global_rss = http.get("/rss")

    assert agent_rss.status_code == 200
    assert "Visible Clip" in agent_rss.text
    assert "Removed Clip" not in agent_rss.text
    assert banned_rss.status_code == 404
    assert global_rss.status_code == 200
    assert "Visible Clip" in global_rss.text
    assert "Removed Clip" not in global_rss.text
    assert "Banned Clip" not in global_rss.text
