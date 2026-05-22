import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_badges_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_badges_bootstrap.db")

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
    db_path = tmp_path / "bottube_badges.db"
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


def _lookup_agent(agent_name: str) -> sqlite3.Row:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        row = db.execute("SELECT * FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
        assert row is not None
        return row


def _insert_video(agent_id: int, video_id: str, *, created_at: float = 5.0) -> None:
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


def _create_referral_code(client, referrer_id: int) -> str:
    with client.session_transaction() as sess:
        sess["user_id"] = referrer_id
        sess["csrf_token"] = "test-csrf"
    resp = client.get("/api/users/me/referral")
    assert resp.status_code == 200
    return resp.get_json()["code"]


def _activate_referred_human(client, code: str, username: str) -> sqlite3.Row:
    with client.session_transaction() as sess:
        sess.pop("user_id", None)
        sess["csrf_token"] = "test-csrf"

    signup_resp = client.post(
        "/signup",
        data={
            "csrf_token": "test-csrf",
            "form_ts": str(time.time() - 10),
            "website": "",
            "username": username,
            "display_name": username.title(),
            "email": f"{username}@example.com",
            "password": "password123",
            "confirm_password": "password123",
            "ref_code": code,
        },
    )
    assert signup_resp.status_code == 302

    row = _lookup_agent(username)
    api_key = row["api_key"]
    assert client.patch(
        "/api/agents/me/profile",
        headers={"X-API-Key": api_key},
        json={"bio": f"{username} bio", "avatar_url": f"https://example.com/{username}.jpg"},
    ).status_code == 200
    assert client.post(
        "/api/agents/me/wallet",
        headers={"X-API-Key": api_key},
        json={"rtc_wallet": f"RTC{username[:1] * 40}"},
    ).status_code == 200
    _insert_video(int(row["id"]), f"{username}video01")
    return _lookup_agent(username)


def _activate_referred_agent(client, code: str, agent_name: str) -> sqlite3.Row:
    reg_resp = client.post(
        "/api/register",
        json={
            "agent_name": agent_name,
            "display_name": agent_name.title(),
            "bio": f"{agent_name} bio",
            "avatar_url": f"https://example.com/{agent_name}.jpg",
            "ref_code": code,
        },
    )
    assert reg_resp.status_code == 201
    api_key = reg_resp.get_json()["api_key"]
    row = _lookup_agent(agent_name)
    assert client.post(
        "/api/agents/me/wallet",
        headers={"X-API-Key": api_key},
        json={"rtc_wallet": f"RTC{agent_name[:1] * 40}"},
    ).status_code == 200
    _insert_video(int(row["id"]), f"{agent_name}video01")
    return _lookup_agent(agent_name)


def test_badge_assignment_renders_on_public_surfaces_and_can_be_removed(client):
    creator_id = _insert_agent("founderhuman", "bottube_sk_founderhuman", is_human=True)
    _insert_video(creator_id, "founderwatch1")

    assign_resp = client.post(
        "/api/admin/badges/assign",
        headers={"X-Admin-Key": "test-admin"},
        json={
            "agent_name": "founderhuman",
            "badge_key": "early_human_bottube",
            "cohort_number": 7,
            "source_campaign": "rustchain-bounties#1584",
            "notes": "manual founding grant",
        },
    )
    assert assign_resp.status_code == 200
    badge_id = assign_resp.get_json()["badge"]["id"]

    list_resp = client.get("/api/admin/badges", headers={"X-Admin-Key": "test-admin"})
    assert list_resp.status_code == 200
    assert list_resp.get_json()["total"] == 1

    agent_resp = client.get("/api/agents/founderhuman")
    assert agent_resp.status_code == 200
    agent_badges = agent_resp.get_json()["agent"]["badges"]
    assert len(agent_badges) == 1
    assert agent_badges[0]["badge_key"] == "early_human_bottube"
    assert agent_badges[0]["cohort_number"] == 7

    channel_resp = client.get("/agent/founderhuman")
    assert channel_resp.status_code == 200
    channel_html = channel_resp.get_data(as_text=True)
    assert "Early Human Adopter" in channel_html
    assert "BoTTube" in channel_html
    assert "founding-badge--human" in channel_html

    watch_resp = client.get("/watch/founderwatch1")
    assert watch_resp.status_code == 200
    watch_html = watch_resp.get_data(as_text=True)
    assert "Early Human Adopter" in watch_html
    assert "founding-badge--human" in watch_html

    with client.session_transaction() as sess:
        sess["user_id"] = creator_id
        sess["csrf_token"] = "test-csrf"
    dash_resp = client.get("/dashboard")
    assert dash_resp.status_code == 200
    dash_html = dash_resp.get_data(as_text=True)
    assert "Founding badges" in dash_html
    assert "Permanent founder identity markers" in dash_html

    remove_resp = client.post(
        f"/api/admin/badges/{badge_id}/remove",
        headers={"X-Admin-Key": "test-admin"},
        json={"removed_by": "reviewer"},
    )
    assert remove_resp.status_code == 200
    assert remove_resp.get_json()["badge"]["is_active"] is False

    after_resp = client.get("/api/agents/founderhuman")
    assert after_resp.status_code == 200
    assert after_resp.get_json()["agent"]["badges"] == []


def test_admin_badge_mutations_reject_malformed_json_inputs(client):
    creator_id = _insert_agent("badgeshape", "bottube_sk_badgeshape", is_human=True)

    non_object_resp = client.post(
        "/api/admin/badges/assign",
        headers={"X-Admin-Key": "test-admin"},
        json=["not", "an", "object"],
    )
    assert non_object_resp.status_code == 400
    assert non_object_resp.get_json()["error"] == "JSON object required"

    non_string_badge = client.post(
        "/api/admin/badges/assign",
        headers={"X-Admin-Key": "test-admin"},
        json={"agent_id": creator_id, "badge_key": ["early_human_bottube"]},
    )
    assert non_string_badge.status_code == 400
    assert non_string_badge.get_json()["error"] == "badge_key must be a string"

    non_string_notes = client.post(
        "/api/admin/badges/assign",
        headers={"X-Admin-Key": "test-admin"},
        json={
            "agent_id": creator_id,
            "badge_key": "early_human_bottube",
            "notes": {"text": "manual founding grant"},
        },
    )
    assert non_string_notes.status_code == 400
    assert non_string_notes.get_json()["error"] == "notes must be a string"

    falsey_string_fields = [
        ("agent_name", False, "agent_name must be a string", {}),
        ("source_campaign", False, "source_campaign must be a string",
         {"agent_id": creator_id}),
        ("notes", False, "notes must be a string", {"agent_id": creator_id}),
        ("awarded_by", False, "awarded_by must be a string",
         {"agent_id": creator_id}),
    ]
    for field, value, expected_error, target_fields in falsey_string_fields:
        payload = {
            "badge_key": "early_human_bottube",
            **target_fields,
            field: value,
        }
        resp = client.post(
            "/api/admin/badges/assign",
            headers={"X-Admin-Key": "test-admin"},
            json=payload,
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == expected_error

    assign_resp = client.post(
        "/api/admin/badges/assign",
        headers={"X-Admin-Key": "test-admin"},
        json={"agent_id": creator_id, "badge_key": "early_human_bottube"},
    )
    assert assign_resp.status_code == 200
    badge_id = assign_resp.get_json()["badge"]["id"]

    bad_remove = client.post(
        f"/api/admin/badges/{badge_id}/remove",
        headers={"X-Admin-Key": "test-admin"},
        json={"removed_by": {"name": "reviewer"}},
    )
    assert bad_remove.status_code == 400
    assert bad_remove.get_json()["error"] == "removed_by must be a string"

    falsey_remove = client.post(
        f"/api/admin/badges/{badge_id}/remove",
        headers={"X-Admin-Key": "test-admin"},
        json={"removed_by": False},
    )
    assert falsey_remove.status_code == 400
    assert falsey_remove.get_json()["error"] == "removed_by must be a string"


def test_badge_candidates_follow_referral_activation_and_scout_thresholds(client):
    referrer_id = _insert_agent("captainleet", "bottube_sk_captainleet", is_human=True)
    code = _create_referral_code(client, referrer_id)

    _activate_referred_human(client, code, "humana")
    _activate_referred_human(client, code, "humanb")
    _activate_referred_human(client, code, "humanc")
    _activate_referred_agent(client, code, "agentprime")

    candidate_resp = client.get("/api/admin/badges/candidates", headers={"X-Admin-Key": "test-admin"})
    assert candidate_resp.status_code == 200
    candidates = candidate_resp.get_json()["candidates"]

    human_badges = [
        row for row in candidates
        if row["agent"]["agent_name"] == "humana" and row["badge_key"] == "early_human_bottube"
    ]
    assert len(human_badges) == 1
    assert human_badges[0]["cohort_number"] == 1
    assert human_badges[0]["source_campaign"] == "rustchain-bounties#1584"

    rustchain_badges = [
        row for row in candidates
        if row["agent"]["agent_name"] == "humana" and row["badge_key"] == "early_human_rustchain"
    ]
    assert len(rustchain_badges) == 1
    assert rustchain_badges[0]["cohort_number"] == 1

    agent_badges = [
        row for row in candidates
        if row["agent"]["agent_name"] == "agentprime" and row["badge_key"] == "early_agent_bottube"
    ]
    assert len(agent_badges) == 1
    assert agent_badges[0]["cohort_number"] == 1
    assert agent_badges[0]["source_campaign"] == "rustchain-bounties#1585"

    scout_badges = [
        row for row in candidates
        if row["agent"]["agent_name"] == "captainleet" and row["badge_key"] == "founding_scout_human"
    ]
    assert len(scout_badges) == 1
    assert scout_badges[0]["evidence"]["pair_count"] == 3
    assert 3 in scout_badges[0]["evidence"]["bonus_thresholds_reached"]
