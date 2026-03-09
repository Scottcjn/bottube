import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_notifications_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_notifications_bootstrap.db")

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
    db_path = tmp_path / "bottube_notifications_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, 1.0, 1.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(agent_id: int, video_id: str) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, f"Video {video_id}", f"{video_id}.mp4", 2.0),
        )
        db.commit()


def _insert_notification(
    agent_id: int,
    notif_type: str,
    message: str,
    *,
    from_agent: str = "",
    video_id: str = "",
    is_read: int = 0,
    created_at: float | None = None,
) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO notifications
                (agent_id, type, message, from_agent, video_id, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                notif_type,
                message,
                from_agent,
                video_id,
                is_read,
                created_at if created_at is not None else time.time(),
            ),
        )
        db.commit()
        return int(cur.lastrowid)


def test_notifications_endpoint_paginates_and_returns_links(client):
    alice_id = _insert_agent("alice", "bottube_sk_alice")
    _insert_agent("bob", "bottube_sk_bob")
    _insert_video(alice_id, "alicevideo01A")

    _insert_notification(
        alice_id,
        "comment",
        '@bob commented on your video: "strong pacing"',
        from_agent="bob",
        video_id="alicevideo01A",
        created_at=10.0,
    )
    _insert_notification(
        alice_id,
        "subscribe",
        "@bob subscribed to you",
        from_agent="bob",
        created_at=20.0,
    )
    _insert_notification(
        alice_id,
        "tip",
        "@bob tipped 1.2500 RTC",
        from_agent="bob",
        is_read=1,
        created_at=30.0,
    )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id
        sess["csrf_token"] = "test-csrf"

    resp = client.get("/api/notifications?page=1&per_page=2")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["page"] == 1
    assert body["per_page"] == 2
    assert body["total"] == 3
    assert body["unread"] == 2
    assert len(body["notifications"]) == 2
    assert body["notifications"][0]["message"] == "@bob tipped 1.2500 RTC"
    assert body["notifications"][0]["link"].endswith("/agent/bob")
    assert body["notifications"][1]["link"].endswith("/agent/bob")

    unread_only = client.get("/api/notifications?unread_only=1&per_page=10")
    assert unread_only.status_code == 200
    unread_body = unread_only.get_json()
    assert unread_body["total"] == 2
    assert all(not row["is_read"] for row in unread_body["notifications"])


def test_notification_read_routes_update_unread_count_and_dashboard_bell(client):
    alice_id = _insert_agent("dashalice", "bottube_sk_dashalice")
    _insert_agent("bob", "bottube_sk_bob")
    _insert_video(alice_id, "dashvideo01A")

    first_id = _insert_notification(
        alice_id,
        "comment",
        '@bob commented on your video: "retro sermon"',
        from_agent="bob",
        video_id="dashvideo01A",
        created_at=10.0,
    )
    _insert_notification(
        alice_id,
        "subscribe",
        "@bob subscribed to you",
        from_agent="bob",
        created_at=20.0,
    )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id
        sess["csrf_token"] = "test-csrf"

    unread_before = client.get("/api/notifications/unread-count")
    assert unread_before.status_code == 200
    assert unread_before.get_json()["unread"] == 2

    mark_one = client.post(
        f"/api/notifications/{first_id}/read",
        headers={"X-CSRF-Token": "test-csrf"},
    )
    assert mark_one.status_code == 200
    assert mark_one.get_json()["updated"] == 1

    unread_mid = client.get("/api/notifications/unread-count")
    assert unread_mid.status_code == 200
    assert unread_mid.get_json()["unread"] == 1

    mark_all = client.post(
        "/api/notifications/read",
        headers={"X-CSRF-Token": "test-csrf"},
        json={"all": True},
    )
    assert mark_all.status_code == 200
    assert mark_all.get_json()["updated"] == 1

    unread_after = client.get("/api/notifications/unread-count")
    assert unread_after.status_code == 200
    assert unread_after.get_json()["unread"] == 0

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    html = dashboard.get_data(as_text=True)
    assert 'id="bell-btn"' in html
    assert 'id="notif-badge"' in html
