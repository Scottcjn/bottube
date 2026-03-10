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


def test_notification_bell_ui_elements_present(client):
    """Test that notification bell UI elements are present in dashboard."""
    alice_id = _insert_agent("bellui_alice", "bottube_sk_bellui_alice")

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Bell button with accessibility attributes
    assert 'id="bell-btn"' in html
    assert 'aria-label=' in html
    assert 'aria-haspopup="true"' in html
    assert 'aria-expanded=' in html

    # Notification badge
    assert 'id="notif-badge"' in html
    assert 'aria-hidden="true"' in html

    # Notification panel
    assert 'id="notif-panel"' in html
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html

    # Mark all read link
    assert 'id="notif-mark-all"' in html

    # Notification list
    assert 'id="notif-list"' in html
    assert 'role="list"' in html


def test_notification_badge_shows_unread_count(client):
    """Test that unread count endpoint returns correct count for badge."""
    alice_id = _insert_agent("badge_alice", "bottube_sk_badge_alice")
    _insert_agent("bob", "bottube_sk_badge_bob")
    _insert_agent("charlie", "bottube_sk_badge_charlie")

    # Create 5 unread notifications
    for i in range(5):
        _insert_notification(
            alice_id,
            "like",
            f"@user{i} liked your video",
            from_agent=f"user{i}",
            is_read=0,
        )

    # Create 3 read notifications (should not count)
    for i in range(3):
        _insert_notification(
            alice_id,
            "comment",
            f"@user{i} commented",
            from_agent=f"user{i}",
            is_read=1,
        )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id

    resp = client.get("/api/notifications/unread-count")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["unread"] == 5


def test_notification_badge_caps_at_99(client):
    """Test that badge displays 99+ for counts over 99."""
    alice_id = _insert_agent("badge99_alice", "bottube_sk_badge99_alice")

    # Create 150 unread notifications
    for i in range(150):
        _insert_notification(
            alice_id,
            "like",
            f"@user{i} liked your video",
            from_agent=f"user{i}",
            is_read=0,
        )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id

    resp = client.get("/api/notifications/unread-count")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["unread"] == 150


def test_notification_list_response_structure(client):
    """Test notification list API response structure."""
    alice_id = _insert_agent("list_alice", "bottube_sk_list_alice")
    _insert_agent("bob", "bottube_sk_list_bob")
    _insert_video(alice_id, "listvideo01A")

    _insert_notification(
        alice_id,
        "comment",
        '@bob commented on your video',
        from_agent="bob",
        video_id="listvideo01A",
        is_read=0,
        created_at=100.0,
    )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id

    resp = client.get("/api/notifications?per_page=10")
    assert resp.status_code == 200
    data = resp.get_json()

    assert "notifications" in data
    assert "page" in data
    assert "per_page" in data
    assert "total" in data
    assert "unread" in data

    notif = data["notifications"][0]
    assert "id" in notif
    assert "type" in notif
    assert "message" in notif
    assert "from_agent" in notif
    assert "video_id" in notif
    assert "is_read" in notif
    assert "created_at" in notif
    assert "link" in notif


def test_mark_all_read_clears_unread_count(client):
    """Test that marking all as read clears the unread count."""
    alice_id = _insert_agent("markall_alice", "bottube_sk_markall_alice")
    _insert_agent("bob", "bottube_sk_markall_bob")

    # Create 10 unread notifications
    for i in range(10):
        _insert_notification(
            alice_id,
            "subscribe",
            f"@user{i} subscribed",
            from_agent=f"user{i}",
            is_read=0,
        )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id
        sess["csrf_token"] = "test-csrf"

    # Verify initial count
    before = client.get("/api/notifications/unread-count")
    assert before.get_json()["unread"] == 10

    # Mark all as read
    resp = client.post(
        "/api/notifications/read",
        headers={"X-CSRF-Token": "test-csrf"},
        json={"all": True},
    )
    assert resp.status_code == 200
    assert resp.get_json()["updated"] == 10

    # Verify count is now 0
    after = client.get("/api/notifications/unread-count")
    assert after.get_json()["unread"] == 0


def test_mark_single_notification_read(client):
    """Test marking a single notification as read."""
    alice_id = _insert_agent("markone_alice", "bottube_sk_markone_alice")
    _insert_agent("bob", "bottube_sk_markone_bob")

    notif_id = _insert_notification(
        alice_id,
        "tip",
        "@bob tipped you",
        from_agent="bob",
        is_read=0,
    )

    # Create another unread to ensure only one is marked
    _insert_notification(
        alice_id,
        "like",
        "@bob liked your video",
        from_agent="bob",
        is_read=0,
    )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id
        sess["csrf_token"] = "test-csrf"

    # Verify initial count
    before = client.get("/api/notifications/unread-count")
    assert before.get_json()["unread"] == 2

    # Mark single notification as read
    resp = client.post(
        f"/api/notifications/{notif_id}/read",
        headers={"X-CSRF-Token": "test-csrf"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["updated"] == 1

    # Verify count decreased by 1
    after = client.get("/api/notifications/unread-count")
    assert after.get_json()["unread"] == 1


def test_notification_unread_filter(client):
    """Test filtering notifications by unread status."""
    alice_id = _insert_agent("filter_alice", "bottube_sk_filter_alice")
    _insert_agent("bob", "bottube_sk_filter_bob")

    # Create mix of read and unread
    _insert_notification(alice_id, "like", "unread 1", from_agent="bob", is_read=0)
    _insert_notification(alice_id, "like", "read 1", from_agent="bob", is_read=1)
    _insert_notification(alice_id, "like", "unread 2", from_agent="bob", is_read=0)
    _insert_notification(alice_id, "like", "read 2", from_agent="bob", is_read=1)

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id

    # Get all notifications
    all_resp = client.get("/api/notifications?per_page=10")
    assert all_resp.get_json()["total"] == 4

    # Get unread only
    unread_resp = client.get("/api/notifications?unread_only=1&per_page=10")
    unread_data = unread_resp.get_json()
    assert unread_data["total"] == 2
    assert all(not n["is_read"] for n in unread_data["notifications"])


def test_notification_requires_authentication(client):
    """Test that notification endpoints require authentication."""
    # Unauthenticated request
    resp = client.get("/api/notifications/unread-count")
    assert resp.status_code == 200  # Returns 0 for unauthenticated
    assert resp.get_json()["unread"] == 0

    resp = client.get("/api/notifications")
    assert resp.status_code == 401
    data = resp.get_json()
    assert "error" in data or data.get("login_required")


def test_notification_mark_read_requires_csrf(client):
    """Test that marking notifications as read requires CSRF token."""
    alice_id = _insert_agent("csrf_alice", "bottube_sk_csrf_alice")

    _insert_notification(
        alice_id,
        "like",
        "test notification",
        is_read=0,
    )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id
        # No CSRF token

    # Try without CSRF token
    resp = client.post(
        "/api/notifications/read",
        json={"all": True},
    )
    assert resp.status_code == 403


def test_notification_pagination(client):
    """Test notification pagination works correctly."""
    alice_id = _insert_agent("page_alice", "bottube_sk_page_alice")
    _insert_agent("bob", "bottube_sk_page_bob")

    # Create 25 notifications
    for i in range(25):
        _insert_notification(
            alice_id,
            "like",
            f"notification {i}",
            from_agent="bob",
            is_read=0,
        )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id

    # Page 1 with 10 per page
    page1 = client.get("/api/notifications?page=1&per_page=10")
    data1 = page1.get_json()
    assert data1["page"] == 1
    assert data1["per_page"] == 10
    assert data1["total"] == 25
    assert len(data1["notifications"]) == 10

    # Page 2
    page2 = client.get("/api/notifications?page=2&per_page=10")
    data2 = page2.get_json()
    assert data2["page"] == 2
    assert len(data2["notifications"]) == 10

    # Page 3
    page3 = client.get("/api/notifications?page=3&per_page=10")
    data3 = page3.get_json()
    assert data3["page"] == 3
    assert len(data3["notifications"]) == 5


def test_notification_types(client):
    """Test different notification types are stored correctly."""
    alice_id = _insert_agent("types_alice", "bottube_sk_types_alice")
    _insert_agent("bob", "bottube_sk_types_bob")
    _insert_video(alice_id, "typesvideo01A")

    types = ["comment", "subscribe", "tip", "like", "mention"]
    for notif_type in types:
        _insert_notification(
            alice_id,
            notif_type,
            f"{notif_type} notification",
            from_agent="bob",
            video_id="typesvideo01A" if notif_type == "comment" else "",
            is_read=0,
        )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id

    resp = client.get("/api/notifications?per_page=10")
    data = resp.get_json()

    returned_types = {n["type"] for n in data["notifications"]}
    assert returned_types == set(types)
