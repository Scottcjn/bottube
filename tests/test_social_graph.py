import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_social_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_social_bootstrap.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_social_graph_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, created_at: float) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', ?, ?)
            """,
            (agent_name, agent_name.title(), f"bottube_sk_{agent_name}", created_at, created_at),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(video_id: str, agent_id: int, created_at: float) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, f"Video {video_id}", f"{video_id}.mp4", created_at),
        )
        db.commit()


def _insert_comment(video_id: str, agent_id: int, content: str, created_at: float) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, agent_id, content, created_at),
        )
        db.commit()


def _insert_vote(video_id: str, agent_id: int, vote: int, created_at: float) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO votes (agent_id, video_id, vote, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (agent_id, video_id, vote, created_at),
        )
        db.commit()


def _insert_subscription(follower_id: int, following_id: int, created_at: float) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO subscriptions (follower_id, following_id, created_at)
            VALUES (?, ?, ?)
            """,
            (follower_id, following_id, created_at),
        )
        db.commit()


def _seed_interaction_data():
    t = 1000.0
    alice_id = _insert_agent("alice", t)
    bob_id = _insert_agent("bob", t + 1)
    carol_id = _insert_agent("carol", t + 2)

    _insert_video("alice_vid_01", alice_id, t + 10)
    _insert_video("bob_vid_001", bob_id, t + 11)
    _insert_video("carol_vid01", carol_id, t + 12)

    # Incoming interactions for alice.
    _insert_comment("alice_vid_01", bob_id, "great cut", t + 20)
    _insert_comment("alice_vid_01", bob_id, "nice pacing", t + 21)
    _insert_comment("alice_vid_01", carol_id, "solid intro", t + 22)
    _insert_vote("alice_vid_01", bob_id, 1, t + 23)
    _insert_vote("alice_vid_01", carol_id, 1, t + 24)
    _insert_subscription(bob_id, alice_id, t + 25)
    _insert_subscription(carol_id, alice_id, t + 26)

    # Outgoing interactions from alice.
    _insert_comment("bob_vid_001", alice_id, "love the style", t + 30)
    _insert_comment("bob_vid_001", alice_id, "clean framing", t + 31)
    _insert_comment("bob_vid_001", alice_id, "nice loops", t + 32)
    _insert_comment("carol_vid01", alice_id, "great color grade", t + 33)
    _insert_vote("bob_vid_001", alice_id, 1, t + 34)
    _insert_vote("carol_vid01", alice_id, 1, t + 35)
    _insert_subscription(alice_id, bob_id, t + 36)
    _insert_subscription(alice_id, carol_id, t + 37)


def test_social_graph_has_expected_keys_and_limit(client):
    _seed_interaction_data()

    resp = client.get("/api/social/graph?limit=1")
    assert resp.status_code == 200
    body = resp.get_json()

    assert {"network", "top_pairs", "most_connected"} <= set(body.keys())
    assert {"total_agents", "total_subscriptions", "active_commenters", "active_likers"} <= set(
        body["network"].keys()
    )
    assert body["network"]["total_agents"] == 3
    assert len(body["top_pairs"]) == 1
    assert len(body["most_connected"]) >= 1

    top_pair = body["top_pairs"][0]
    assert {"from", "from_display", "to", "to_display", "comments", "likes", "strength"} <= set(
        top_pair.keys()
    )


def test_agent_interactions_shape_not_found_and_limit(client):
    _seed_interaction_data()

    not_found = client.get("/api/agents/no_such_agent/interactions")
    assert not_found.status_code == 404
    assert not_found.get_json()["error"] == "Agent not found"

    resp = client.get("/api/agents/alice/interactions?limit=1")
    assert resp.status_code == 200
    body = resp.get_json()

    assert {"agent", "incoming", "outgoing"} <= set(body.keys())
    assert {"commenters", "likers", "followers"} <= set(body["incoming"].keys())

    # limit=1 should apply to each section.
    assert len(body["incoming"]["commenters"]) == 1
    assert len(body["incoming"]["likers"]) == 1
    assert len(body["incoming"]["followers"]) == 1
    assert len(body["outgoing"]) == 1

    commenter = body["incoming"]["commenters"][0]
    assert {"agent_name", "display_name", "avatar_url", "comment_count", "last_at"} <= set(
        commenter.keys()
    )

    liker = body["incoming"]["likers"][0]
    assert {"agent_name", "display_name", "avatar_url", "like_count", "last_at"} <= set(
        liker.keys()
    )

    follower = body["incoming"]["followers"][0]
    assert {"agent_name", "display_name", "avatar_url", "subscribed_at"} <= set(
        follower.keys()
    )

    outgoing = body["outgoing"][0]
    assert {"agent_name", "display_name", "avatar_url", "comments_given", "likes_given", "total"} <= set(
        outgoing.keys()
    )
