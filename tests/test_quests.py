import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_bootstrap.db")

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
    db_path = tmp_path / "bottube_test.db"
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


def _insert_comment(agent_id: int, video_id: str, content: str, created_at: float = 3.0) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, agent_id, content, created_at),
        )
        db.commit()
        return int(cur.lastrowid)


def _quest_reward(quest_key: str) -> float:
    return next(q["reward_rtc"] for q in bottube_server.DEFAULT_QUESTS if q["quest_key"] == quest_key)


def test_quests_endpoint_unlocks_onboarding_flow(client):
    alice_id = _insert_agent("alice", "bottube_sk_alice")
    bob_id = _insert_agent("bob", "bottube_sk_bob")
    _insert_video(alice_id, "alicevideo1A")
    _insert_video(bob_id, "bobvideo01B")

    resp = client.patch(
        "/api/agents/me/profile",
        headers={"X-API-Key": "bottube_sk_alice"},
        json={"bio": "retro video builder", "avatar_url": "https://example.com/alice.jpg"},
    )
    assert resp.status_code == 200

    resp = client.post(
        "/api/agents/bob/subscribe",
        headers={"X-API-Key": "bottube_sk_alice"},
    )
    assert resp.status_code == 200

    resp = client.post(
        "/api/videos/bobvideo01B/comment",
        headers={"X-API-Key": "bottube_sk_alice"},
        json={"content": "clean build, strong pacing"},
    )
    assert resp.status_code == 201

    resp = client.get("/api/quests/me", headers={"X-API-Key": "bottube_sk_alice"})
    assert resp.status_code == 200
    body = resp.get_json()
    completed = {q["quest_key"] for q in body["quests"] if q["completed"]}
    assert {"profile_complete", "first_upload", "first_comment", "first_follow"} <= completed

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        rtc_balance = conn.execute(
            "SELECT rtc_balance FROM agents WHERE agent_name = 'alice'"
        ).fetchone()[0]
        quest_reasons = conn.execute(
            "SELECT reason FROM earnings WHERE agent_id = ? ORDER BY reason ASC",
            (alice_id,),
        ).fetchall()
    finally:
        conn.close()

    assert round(rtc_balance, 4) == round(
        bottube_server.RTC_REWARD_COMMENT
        + _quest_reward("profile_complete")
        + _quest_reward("first_upload")
        + _quest_reward("first_comment")
        + _quest_reward("first_follow"),
        4,
    )
    assert {
        "quest_complete:profile_complete",
        "quest_complete:first_upload",
        "quest_complete:first_comment",
        "quest_complete:first_follow",
    } <= {row[0] for row in quest_reasons}


def test_quest_rewards_are_idempotent_and_leaderboard_updates(client):
    alice_id = _insert_agent("alice2", "bottube_sk_alice2")
    bob_id = _insert_agent("bob2", "bottube_sk_bob2")
    _insert_video(alice_id, "alicevide2A")
    _insert_video(bob_id, "bobvideo02B")

    client.patch(
        "/api/agents/me/profile",
        headers={"X-API-Key": "bottube_sk_alice2"},
        json={"bio": "a builder", "avatar_url": "https://example.com/alice2.jpg"},
    )
    client.post("/api/agents/bob2/subscribe", headers={"X-API-Key": "bottube_sk_alice2"})
    client.get("/api/quests/me", headers={"X-API-Key": "bottube_sk_alice2"})
    client.get("/api/quests/me", headers={"X-API-Key": "bottube_sk_alice2"})

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        quest_count = conn.execute(
            "SELECT COUNT(*) FROM earnings WHERE agent_id = ? AND reason LIKE 'quest_complete:%'",
            (alice_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert quest_count == 3

    resp = client.get("/api/quests/leaderboard?limit=5")
    assert resp.status_code == 200
    leaderboard = resp.get_json()["leaderboard"]
    assert leaderboard[0]["agent_name"] == "alice2"
    assert leaderboard[0]["completed_count"] >= 3


def test_dashboard_renders_quest_board_and_streak(client):
    alice_id = _insert_agent("dashalice", "bottube_sk_dashalice")
    _insert_video(alice_id, "dashvideo01A")
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        bottube_server._queue_moderation_hold(
            db,
            target_type="video",
            target_ref="dashvideo01A",
            target_agent_id=alice_id,
            source="test_dashboard",
            reason="test coaching hold",
            coach_note="Tighten the metadata and pacing before the next upload.",
        )
        db.commit()

    client.patch(
        "/api/agents/me/profile",
        headers={"X-API-Key": "bottube_sk_dashalice"},
        json={"bio": "dashboard builder", "avatar_url": "https://example.com/dashalice.jpg"},
    )

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id
        sess["csrf_token"] = "test-csrf"

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Quest Board" in html
    assert "day streak" in html
    assert "Coaching & Review" in html


def test_dashboard_shows_onboarding_card_before_referral_for_zero_video_creator(client):
    alice_id = _insert_agent("freshdash", "bottube_sk_freshdash")

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id
        sess["csrf_token"] = "test-csrf"

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Start your first upload" in html
    assert "/upload" in html
    assert "/developers" in html
    assert "/api/docs" in html
    assert "500MB max upload" in html
    assert "8s max duration" in html
    assert "720×720 max output bounds" in html
    assert "H.264 MP4 final transcode" in html
    assert "~2MB final size target after transcoding" in html
    assert html.index("Start your first upload") < html.index("Referral link")


def test_dashboard_hides_onboarding_card_after_first_upload(client):
    alice_id = _insert_agent("dashready", "bottube_sk_dashready")
    _insert_video(alice_id, "dashready01A")

    with client.session_transaction() as sess:
        sess["user_id"] = alice_id
        sess["csrf_token"] = "test-csrf"

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Start your first upload" not in html


def test_suspicious_comment_reward_is_held_for_review(client):
    commenter_id = _insert_agent("holdalice", "bottube_sk_holdalice")
    target_id = _insert_agent("holdbob", "bottube_sk_holdbob")
    _insert_video(target_id, "holdvideo01A")
    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        conn.execute("UPDATE agents SET created_at = ? WHERE id = ?", (time.time(), commenter_id))
        conn.commit()
    finally:
        conn.close()

    resp = client.post(
        "/api/videos/holdvideo01A/comment",
        headers={"X-API-Key": "bottube_sk_holdalice"},
        json={"content": "loooooool https://spam.test"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["reward"]["held"] is True
    assert body["reward"]["awarded"] is False

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        hold_count = conn.execute(
            "SELECT COUNT(*) FROM reward_holds WHERE agent_id = ? AND status = 'pending'",
            (commenter_id,),
        ).fetchone()[0]
        comment_earnings = conn.execute(
            "SELECT COUNT(*) FROM earnings WHERE agent_id = ? AND reason = 'comment'",
            (commenter_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert hold_count == 1
    assert comment_earnings == 0


def test_admin_ban_defaults_to_coaching_hold_instead_of_ban(client):
    agent_id = _insert_agent("coachme", "bottube_sk_coachme")

    resp = client.post(
        "/api/admin/ban",
        headers={"X-Admin-Key": bottube_server.ADMIN_KEY},
        json={"agent_name": "coachme", "reason": "repetitive spam pattern"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["held_for_review"] == "coachme"
    assert body["forced"] is False

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        is_banned = conn.execute(
            "SELECT is_banned FROM agents WHERE id = ?",
            (agent_id,),
        ).fetchone()[0]
        hold_count = conn.execute(
            "SELECT COUNT(*) FROM moderation_holds WHERE target_type = 'agent' AND target_ref = 'coachme'",
        ).fetchone()[0]
        moderation_messages = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE to_agent = 'coachme' AND message_type = 'moderation'",
        ).fetchone()[0]
    finally:
        conn.close()

    assert is_banned == 0
    assert hold_count == 1
    assert moderation_messages == 1


def test_report_threshold_queues_hold_without_auto_removal(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_ownerbot")
    _insert_video(owner_id, "ownerclip01A")
    _insert_agent("reporter1", "bottube_sk_reporter1")
    _insert_agent("reporter2", "bottube_sk_reporter2")
    _insert_agent("reporter3", "bottube_sk_reporter3")

    for reporter in ("bottube_sk_reporter1", "bottube_sk_reporter2"):
        resp = client.post(
            "/api/videos/ownerclip01A/report",
            headers={"X-API-Key": reporter},
            json={"reason": "spam", "details": "low-signal clip"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["flagged_for_review"] is False

    resp = client.post(
        "/api/videos/ownerclip01A/report",
        headers={"X-API-Key": "bottube_sk_reporter3"},
        json={"reason": "spam", "details": "third report"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["flagged_for_review"] is True

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        video_row = conn.execute(
            "SELECT is_removed, removed_reason FROM videos WHERE video_id = 'ownerclip01A'",
        ).fetchone()
        hold_count = conn.execute(
            "SELECT COUNT(*) FROM moderation_holds WHERE target_type = 'video' AND target_ref = 'ownerclip01A' AND source = 'community_reports'",
        ).fetchone()[0]
        moderation_messages = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE to_agent = 'ownerbot' AND message_type = 'moderation'",
        ).fetchone()[0]
    finally:
        conn.close()

    assert video_row[0] == 0
    assert video_row[1] in ("", None)
    assert hold_count == 1
    assert moderation_messages == 1


def test_admin_resolve_report_defaults_to_coach_without_deleting_comment(client):
    owner_id = _insert_agent("commentowner", "bottube_sk_commentowner")
    reporter_id = _insert_agent("commentreporter", "bottube_sk_commentreporter")
    _insert_video(owner_id, "commentclip1A")
    comment_id = _insert_comment(owner_id, "commentclip1A", "same phrase over and over")
    assert reporter_id > 0

    resp = client.post(
        f"/api/comments/{comment_id}/report",
        headers={"X-API-Key": "bottube_sk_commentreporter"},
        json={"reason": "spam", "details": "repetitive"},
    )
    assert resp.status_code == 200

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        report_id = conn.execute(
            "SELECT id FROM reports WHERE comment_id = ? ORDER BY id DESC LIMIT 1",
            (comment_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    resp = client.post(
        f"/api/admin/reports/{report_id}/resolve",
        headers={"X-Admin-Key": bottube_server.ADMIN_KEY},
        json={},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "coach"
    assert body["forced"] is False

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        comment_exists = conn.execute(
            "SELECT COUNT(*) FROM comments WHERE id = ?",
            (comment_id,),
        ).fetchone()[0]
        hold_count = conn.execute(
            "SELECT COUNT(*) FROM moderation_holds WHERE target_type = 'comment' AND target_ref = ? AND source = 'admin_report_resolution'",
            (str(comment_id),),
        ).fetchone()[0]
        report_status = conn.execute(
            "SELECT status FROM reports WHERE id = ?",
            (report_id,),
        ).fetchone()[0]
        moderation_messages = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE to_agent = 'commentowner' AND message_type = 'moderation'",
        ).fetchone()[0]
    finally:
        conn.close()

    assert comment_exists == 1
    assert hold_count == 1
    assert report_status == "actioned"
    assert moderation_messages == 1


def test_comment_cleanup_defaults_to_hold_without_deleting(client):
    agent_id = _insert_agent("cleanupbot", "bottube_sk_cleanupbot")
    target_id = _insert_agent("cleanupowner", "bottube_sk_cleanupowner")
    _insert_video(target_id, "cleanupvid1A")
    first = _insert_comment(agent_id, "cleanupvid1A", "duplicate note", created_at=10.0)
    second = _insert_comment(agent_id, "cleanupvid1A", "duplicate note", created_at=11.0)
    assert first != second

    resp = client.post(
        "/api/admin/comment-cleanup",
        headers={"X-Admin-Key": bottube_server.ADMIN_KEY},
        json={"remove_dupes": True, "max_similar": 10},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["mode"] == "coach_and_hold"
    assert body["held_duplicates"] >= 1
    assert body["removed_duplicates"] == 0

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        comment_count = conn.execute(
            "SELECT COUNT(*) FROM comments WHERE agent_id = ? AND video_id = 'cleanupvid1A'",
            (agent_id,),
        ).fetchone()[0]
        hold_count = conn.execute(
            "SELECT COUNT(*) FROM moderation_holds WHERE target_type = 'comment' AND source = 'comment_cleanup_duplicate'",
        ).fetchone()[0]
        moderation_messages = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE to_agent = 'cleanupbot' AND message_type = 'moderation'",
        ).fetchone()[0]
    finally:
        conn.close()

    assert comment_count == 2
    assert hold_count >= 1
    assert moderation_messages >= 1


def test_self_view_reward_is_held_for_review(client):
    owner_id = _insert_agent("viewowner", "bottube_sk_viewowner")
    _insert_video(owner_id, "viewhold01A")

    resp = client.get(
        "/api/videos/viewhold01A/view",
        headers={"X-API-Key": "bottube_sk_viewowner", "X-Real-IP": "10.0.0.9"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["reward"]["held"] is True
    assert body["reward"]["awarded"] is False

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        hold_count = conn.execute(
            "SELECT COUNT(*) FROM reward_holds WHERE agent_id = ? AND event_type = 'video_view' AND status = 'pending'",
            (owner_id,),
        ).fetchone()[0]
        reward_count = conn.execute(
            "SELECT COUNT(*) FROM earnings WHERE agent_id = ? AND reason = 'video_view'",
            (owner_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert hold_count == 1
    assert reward_count == 0


def test_like_reward_hold_can_be_credited_by_admin(client):
    owner_id = _insert_agent("likeowner", "bottube_sk_likeowner")
    voter_id = _insert_agent("likevoter", "bottube_sk_likevoter")
    assert voter_id > 0
    _insert_video(owner_id, "likehold09A")

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        for idx in range(15):
            video_id = f"likehist{idx:02d}A"
            db.execute(
                "INSERT INTO videos (video_id, agent_id, title, filename, created_at, is_removed) VALUES (?, ?, ?, ?, ?, 0)",
                (video_id, owner_id, f"History {idx}", f"{video_id}.mp4", 5.0 + idx),
            )
            db.execute(
                "INSERT INTO votes (agent_id, video_id, vote, created_at) VALUES (?, ?, 1, ?)",
                (voter_id, video_id, time.time()),
            )
        db.commit()

    resp = client.post(
        "/api/videos/likehold09A/vote",
        headers={"X-API-Key": "bottube_sk_likevoter"},
        json={"vote": 1},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["reward"]["held"] is True

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        hold_id = conn.execute(
            """
            SELECT id FROM reward_holds
            WHERE agent_id = ? AND event_type = 'like_received' AND event_ref = ?
            """,
            (owner_id, f"likehold09A:{voter_id}"),
        ).fetchone()[0]
    finally:
        conn.close()

    resp = client.post(
        f"/api/admin/reward-holds/{hold_id}/resolve",
        headers={"X-Admin-Key": bottube_server.ADMIN_KEY},
        json={"action": "credit", "note": "manual review approved"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "credited"

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        hold_status = conn.execute(
            "SELECT status FROM reward_holds WHERE id = ?",
            (hold_id,),
        ).fetchone()[0]
        reward_count = conn.execute(
            "SELECT COUNT(*) FROM earnings WHERE agent_id = ? AND reason = 'like_received_reviewed'",
            (owner_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert hold_status == "credited"
    assert reward_count == 1


def test_moderation_hold_release_restores_video(client):
    owner_id = _insert_agent("releaseowner", "bottube_sk_releaseowner")
    _insert_video(owner_id, "releasevid1A")

    resp = client.post(
        "/api/admin/remove-video",
        headers={"X-Admin-Key": bottube_server.ADMIN_KEY},
        json={"video_id": "releasevid1A", "reason": "needs coaching"},
    )
    assert resp.status_code == 200
    hold_id = resp.get_json()["hold_id"]

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        is_removed = conn.execute(
            "SELECT is_removed FROM videos WHERE video_id = 'releasevid1A'",
        ).fetchone()[0]
    finally:
        conn.close()
    assert is_removed == 1

    resp = client.post(
        f"/api/admin/moderation-holds/{hold_id}/resolve",
        headers={"X-Admin-Key": bottube_server.ADMIN_KEY},
        json={"action": "release", "note": "restored after review"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "released"

    conn = sqlite3.connect(bottube_server.DB_PATH)
    try:
        video_row = conn.execute(
            "SELECT is_removed, removed_reason FROM videos WHERE video_id = 'releasevid1A'",
        ).fetchone()
        hold_status = conn.execute(
            "SELECT status FROM moderation_holds WHERE id = ?",
            (hold_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert video_row[0] == 0
    assert video_row[1] == ""
    assert hold_status == "released"
