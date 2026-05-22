import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_BASE_DIR = "/tmp/bottube_test_public_interaction_visibility"
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
    db_path = tmp_path / "bottube_public_interaction_visibility.db"

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


def _insert_comment(video_id: str, agent_id: int) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, created_at)
            VALUES (?, ?, 'interaction fixture comment', ?)
            """,
            (video_id, agent_id, time.time()),
        )
        db.commit()


def _insert_vote(video_id: str, agent_id: int, vote: int = 1) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO votes (agent_id, video_id, vote, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (agent_id, video_id, vote, time.time()),
        )
        db.commit()


def _insert_subscription(follower_id: int, following_id: int) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO subscriptions (follower_id, following_id, created_at)
            VALUES (?, ?, ?)
            """,
            (follower_id, following_id, time.time()),
        )
        db.commit()


def test_agent_interactions_hide_banned_agents_and_removed_videos(client):
    alice = _insert_agent("alice")
    bob = _insert_agent("bob")
    banned = _insert_agent("banned", is_banned=1)
    carol = _insert_agent("carol")

    _insert_video("alice-visible", alice)
    _insert_video("alice-removed", alice, is_removed=1)
    _insert_video("bob-visible", bob)
    _insert_video("banned-visible", banned)

    _insert_comment("alice-visible", bob)
    _insert_vote("alice-visible", bob)
    _insert_subscription(bob, alice)

    _insert_comment("alice-visible", banned)
    _insert_vote("alice-visible", banned)
    _insert_subscription(banned, alice)

    _insert_comment("alice-removed", carol)
    _insert_vote("alice-removed", carol)

    _insert_comment("bob-visible", alice)
    _insert_vote("bob-visible", alice)
    _insert_comment("banned-visible", alice)
    _insert_vote("banned-visible", alice)

    resp = client.get("/api/agents/alice/interactions")

    assert resp.status_code == 200
    data = resp.get_json()
    incoming = data["incoming"]
    assert [row["agent_name"] for row in incoming["commenters"]] == ["bob"]
    assert [row["agent_name"] for row in incoming["likers"]] == ["bob"]
    assert [row["agent_name"] for row in incoming["followers"]] == ["bob"]
    assert [row["agent_name"] for row in data["outgoing"]] == ["bob"]


def test_agent_interactions_hide_banned_target_agent(client):
    banned = _insert_agent("banned", is_banned=1)
    bob = _insert_agent("bob")
    _insert_video("banned-visible", banned)
    _insert_comment("banned-visible", bob)

    resp = client.get("/api/agents/banned/interactions")

    assert resp.status_code == 404


def test_social_graph_excludes_banned_agents_and_removed_video_edges(client):
    alice = _insert_agent("alice")
    bob = _insert_agent("bob")
    banned = _insert_agent("banned", is_banned=1)
    carol = _insert_agent("carol")

    _insert_video("alice-visible", alice)
    _insert_video("alice-removed", alice, is_removed=1)
    _insert_video("bob-visible", bob)
    _insert_video("banned-visible", banned)

    _insert_comment("alice-visible", bob)
    _insert_vote("alice-visible", bob)
    _insert_subscription(bob, alice)

    _insert_comment("alice-visible", banned)
    _insert_vote("alice-visible", banned)
    _insert_subscription(banned, alice)
    _insert_subscription(alice, banned)

    _insert_comment("alice-removed", carol)
    _insert_vote("alice-removed", carol)
    _insert_comment("banned-visible", alice)
    _insert_vote("banned-visible", alice)

    resp = client.get("/api/social/graph?limit=10")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["network"]["total_agents"] == 3
    assert data["network"]["total_subscriptions"] == 1
    assert data["network"]["active_commenters"] == 1
    assert data["network"]["active_likers"] == 1
    assert data["top_pairs"] == [
        {
            "from": "bob",
            "from_display": "Bob",
            "to": "alice",
            "to_display": "Alice",
            "comments": 1,
            "likes": 1,
            "strength": 2,
        }
    ]
    connected_names = {row["agent_name"] for row in data["most_connected"]}
    assert connected_names <= {"alice", "bob"}
