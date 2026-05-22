import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "BOTTUBE_DB_PATH",
    "/tmp/bottube_test_subscription_visibility_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_subscription_visibility_bootstrap.db",
)

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages  # noqa: E402


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server  # noqa: E402

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_subscription_visibility_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(
    agent_name: str,
    created_at: float,
    *,
    is_banned: int = 0,
) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url,
                 created_at, last_active, is_banned)
            VALUES (?, ?, ?, '', '', ?, ?, ?)
            """,
            (
                agent_name,
                agent_name.replace("-", " ").title(),
                f"bottube_sk_{agent_name}",
                created_at,
                created_at,
                is_banned,
            ),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_subscription(
    follower_id: int,
    following_id: int,
    created_at: float,
) -> None:
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


def _insert_video(
    video_id: str,
    agent_id: int,
    created_at: float,
    *,
    is_removed: int = 0,
) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, description, filename,
                 thumbnail, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                agent_id,
                f"Video {video_id}",
                f"Description {video_id}",
                f"{video_id}.mp4",
                f"{video_id}.jpg",
                created_at,
                is_removed,
            ),
        )
        db.commit()


def _api_headers(agent_name: str) -> dict[str, str]:
    return {"X-API-Key": f"bottube_sk_{agent_name}"}


def test_subscribe_rejects_banned_targets(client):
    _insert_agent("alice", 1000.0)
    banned_id = _insert_agent("banned-target", 1001.0, is_banned=1)

    resp = client.post(
        "/api/agents/banned-target/subscribe",
        headers=_api_headers("alice"),
    )

    assert resp.status_code == 404
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        follow_count = db.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE following_id = ?",
            (banned_id,),
        ).fetchone()[0]
    assert follow_count == 0


def test_my_subscriptions_hides_banned_followed_agents(client):
    alice_id = _insert_agent("alice", 1000.0)
    visible_id = _insert_agent("visible-agent", 1001.0)
    banned_id = _insert_agent("banned-target", 1002.0, is_banned=1)
    _insert_subscription(alice_id, banned_id, 1003.0)
    _insert_subscription(alice_id, visible_id, 1004.0)

    resp = client.get(
        "/api/agents/me/subscriptions",
        headers=_api_headers("alice"),
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert [row["agent_name"] for row in data["subscriptions"]] == [
        "visible-agent",
    ]


def test_public_subscribers_hides_banned_targets_and_followers(client):
    target_id = _insert_agent("target", 1000.0)
    visible_follower_id = _insert_agent("visible-follower", 1001.0)
    banned_follower_id = _insert_agent("banned-follower", 1002.0, is_banned=1)
    banned_target_id = _insert_agent("banned-target", 1003.0, is_banned=1)
    _insert_subscription(visible_follower_id, target_id, 1004.0)
    _insert_subscription(banned_follower_id, target_id, 1005.0)
    _insert_subscription(visible_follower_id, banned_target_id, 1006.0)

    resp = client.get("/api/agents/target/subscribers")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert [row["agent_name"] for row in data["subscribers"]] == [
        "visible-follower",
    ]

    banned_resp = client.get("/api/agents/banned-target/subscribers")

    assert banned_resp.status_code == 404


def test_subscription_feed_hides_removed_and_banned_owner_videos(client):
    alice_id = _insert_agent("alice", 1000.0)
    visible_id = _insert_agent("visible-agent", 1001.0)
    banned_id = _insert_agent("banned-target", 1002.0, is_banned=1)
    _insert_subscription(alice_id, visible_id, 1003.0)
    _insert_subscription(alice_id, banned_id, 1004.0)
    _insert_video("visiblevid01", visible_id, 1005.0)
    _insert_video("removedvid01", visible_id, 1006.0, is_removed=1)
    _insert_video("bannedvid01", banned_id, 1007.0)

    resp = client.get("/api/feed/subscriptions", headers=_api_headers("alice"))

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert [row["video_id"] for row in data["videos"]] == ["visiblevid01"]


def test_web_subscribe_rejects_banned_targets(client):
    alice_id = _insert_agent("alice", 1000.0)
    _insert_agent("banned-target", 1001.0, is_banned=1)
    with client.session_transaction() as session:
        session["user_id"] = alice_id
        session["csrf_token"] = "test-csrf-token"

    resp = client.post(
        "/api/agents/banned-target/web-subscribe",
        json={"csrf_token": "test-csrf-token"},
    )

    assert resp.status_code == 404
