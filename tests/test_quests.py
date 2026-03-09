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
