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
    Path(bootstrap_path).unlink(missing_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_referrals.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test-admin", raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str, *, is_human: bool = False) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, 1 if is_human else 0, 1.0, 1.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video_and_mark(agent_id: int, video_id: str, *, created_at: float = 5.0) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, f"Video {video_id}", f"{video_id}.mp4", created_at),
        )
        bottube_server._referral_mark_first_upload(db, agent_id)
        bottube_server._referral_refresh_invite_state(db, agent_id)
        db.commit()


def _lookup_agent(agent_name: str) -> sqlite3.Row:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        row = db.execute("SELECT * FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
        assert row is not None
        return row


@pytest.mark.parametrize("limit", ["abc", "1.5", "0", "-1", "201"])
def test_referral_leaderboard_rejects_invalid_limit(client, limit):
    resp = client.get(f"/api/referrals/leaderboard?limit={limit}")

    assert resp.status_code == 400
    body = resp.get_json()
    assert "limit" in body["error"]


@pytest.mark.parametrize("limit", [None, "1", "200"])
def test_referral_leaderboard_accepts_default_and_boundary_limits(client, limit):
    path = "/api/referrals/leaderboard"
    if limit is not None:
        path = f"{path}?limit={limit}"

    resp = client.get(path)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert isinstance(body["leaderboard"], list)


def test_referral_dashboard_tracks_human_and_agent_funnels(client):
    referrer_id = _insert_agent("founder1337", "bottube_sk_founder", is_human=True)

    with client.session_transaction() as sess:
        sess["user_id"] = referrer_id
        sess["csrf_token"] = "test-csrf"

    resp = client.get("/api/users/me/referral")
    assert resp.status_code == 200
    code = resp.get_json()["code"]

    signup_resp = client.post(
        "/signup",
        data={
            "csrf_token": "test-csrf",
            "form_ts": str(time.time() - 10),
            "website": "",
            "username": "newhuman",
            "display_name": "New Human",
            "email": "human@example.com",
            "password": "password123",
            "confirm_password": "password123",
            "ref_code": code,
        },
    )
    assert signup_resp.status_code == 302

    human = _lookup_agent("newhuman")
    human_key = human["api_key"]
    assert human["referred_by_code"] == code

    assert client.patch(
        "/api/agents/me/profile",
        headers={"X-API-Key": human_key},
        json={"bio": "human builder", "avatar_url": "https://example.com/human.jpg"},
    ).status_code == 200
    assert client.post(
        "/api/agents/me/wallet",
        headers={"X-API-Key": human_key},
        json={"rtc_wallet": f"RTC{'a' * 40}"},
    ).status_code == 200
    _insert_video_and_mark(int(human["id"]), "humanvideo01")

    reg_resp = client.post(
        "/api/register",
        json={
            "agent_name": "botinvite",
            "display_name": "Bot Invite",
            "bio": "agent builder",
            "avatar_url": "https://example.com/bot.jpg",
            "ref_code": code,
        },
    )
    assert reg_resp.status_code == 201
    agent_key = reg_resp.get_json()["api_key"]
    agent = _lookup_agent("botinvite")
    assert agent["referred_by_code"] == code

    assert client.post(
        "/api/agents/me/wallet",
        headers={"X-API-Key": agent_key},
        json={"rtc_wallet": f"RTC{'b' * 40}"},
    ).status_code == 200
    _insert_video_and_mark(int(agent["id"]), "agentvideo01")

    with client.session_transaction() as sess:
        sess["user_id"] = referrer_id
        sess["csrf_token"] = "test-csrf"

    referral_resp = client.get("/api/users/me/referral")
    assert referral_resp.status_code == 200
    summary = referral_resp.get_json()["summary"]
    assert summary["tracks"]["human"]["invited"] == 1
    assert summary["tracks"]["agent"]["invited"] == 1
    assert summary["milestones"]["profile_completed"] == 2
    assert summary["milestones"]["first_public_video"] == 2
    assert summary["milestones"]["first_rtc_native_action"] == 2
    assert summary["fully_activated_pairs"] == 2
    assert summary["pending_review_count"] == 2

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    html = dashboard.get_data(as_text=True)
    assert "Invited Humans" in html
    assert "Invited Agents" in html
    assert "Fully Activated Pairs" in html
    assert "Bonus 3" in html


def test_referral_admin_review_and_export(client):
    referrer_id = _insert_agent("captainref", "bottube_sk_captain", is_human=True)

    with client.session_transaction() as sess:
        sess["user_id"] = referrer_id
        sess["csrf_token"] = "test-csrf"

    code = client.get("/api/users/me/referral").get_json()["code"]

    reg_resp = client.post(
        "/api/register",
        json={
            "agent_name": "reviewbot",
            "display_name": "Review Bot",
            "bio": "route me",
            "avatar_url": "https://example.com/reviewbot.jpg",
            "ref_code": code,
        },
    )
    assert reg_resp.status_code == 201
    api_key = reg_resp.get_json()["api_key"]
    agent = _lookup_agent("reviewbot")

    assert client.post(
        "/api/agents/me/wallet",
        headers={"X-API-Key": api_key},
        json={"rtc_wallet": f"RTC{'c' * 40}"},
    ).status_code == 200
    _insert_video_and_mark(int(agent["id"]), "reviewvideo01")

    admin_resp = client.get("/api/admin/referrals", headers={"X-Admin-Key": "test-admin"})
    assert admin_resp.status_code == 200
    body = admin_resp.get_json()
    assert body["total"] == 1
    row = body["referrals"][0]
    assert row["invitee"]["track"] == "agent"
    assert row["milestones"]["first_public_video"]["evidence_ref"] == "/watch/reviewvideo01"
    assert row["milestones"]["first_rtc_native_action"]["evidence_ref"] == "/settings/wallet"

    review_resp = client.post(
        f"/api/admin/referrals/{row['id']}/review",
        headers={"X-Admin-Key": "test-admin"},
        json={"action": "approve", "note": "clean referral"},
    )
    assert review_resp.status_code == 200
    assert review_resp.get_json()["review_status"] == "approved"

    export_resp = client.get("/api/admin/referrals/export", headers={"X-Admin-Key": "test-admin"})
    assert export_resp.status_code == 200
    export_rows = export_resp.get_json()["rows"]
    assert len(export_rows) == 1
    assert export_rows[0]["review_status"] == "approved"


def test_referral_track_setting_blocks_wrong_funnel(client):
    referrer_id = _insert_agent("humancode", "bottube_sk_humancode")

    resp = client.post(
        "/api/agents/me/referral",
        headers={"X-API-Key": "bottube_sk_humancode"},
        json={"allowed_track": "human"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["allowed_track"] == "human"

    blocked = client.post(
        "/api/register",
        json={"agent_name": "wrongfunnel", "ref_code": body["code"]},
    )
    assert blocked.status_code == 400
    assert "not enabled for agent onboarding" in blocked.get_json()["error"]
