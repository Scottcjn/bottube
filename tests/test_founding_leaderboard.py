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

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_founding_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_founding_bootstrap.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    """Redirect the hardcoded production DB path to the test bootstrap path.

    Import-time code in `paypal_packages`/`bottube_server` opens the real
    `/root/bottube/bottube.db` before the `client` fixture can monkeypatch
    `DB_PATH`, so without this shim just collecting this module would touch
    production data.
    """
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    """Force paypal_packages' schema init onto a clean test bootstrap DB.

    Deletes any stale bootstrap file first so leftover state from a prior
    interrupted run can't leak founding-cohort/badge rows into this run's
    slot-count assertions.
    """
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    Path(bootstrap_path).unlink(missing_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Yield a Flask test client on an isolated DB with a fixed admin key.

    Pins `ADMIN_KEY` to a known value so `_assign_badge` can authenticate
    without depending on whatever admin key the server module happened to
    load from the environment.
    """
    db_path = tmp_path / "bottube_founding.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test-admin", raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str, *, is_human: bool = False) -> int:
    """Insert a minimal agent row directly, bypassing signup/registration.

    Used only for the referrer seed: the leaderboard tests need a referrer
    that already exists before a referral code can be minted, and going
    through the real signup/register flow here would be redundant with the
    referred-activation helpers below.
    """
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
    """Fetch an agent's full row, asserting it exists.

    The assertion here is deliberate: callers use this right after
    signup/registration, so a missing row means account creation silently
    failed and every downstream assertion in the test would otherwise
    fail with a confusing `NoneType` error instead of pointing at the
    actual cause.
    """
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        row = db.execute("SELECT * FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
        assert row is not None
        return row


def _insert_video(agent_id: int, video_id: str, *, created_at: float = 5.0) -> None:
    """Seed a video and drive it through the referral-activation hooks.

    A referred signup alone does not count as "activated" for the
    leaderboard -- the real server only flips that state once the referred
    agent uploads their first video, so this helper calls the same
    `_referral_mark_first_upload`/`_referral_refresh_invite_state` hooks
    the production upload path calls, instead of writing activation flags
    directly and risking a test that passes for reasons the app doesn't.
    """
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
    """Log in as `referrer_id` via the session and fetch their referral code.

    Bypasses the login form entirely by writing straight into the Flask
    session -- what's under test here is the leaderboard/referral logic,
    not authentication, so a direct session write keeps the test focused
    and fast instead of re-proving login works on every referral test.
    """
    with client.session_transaction() as sess:
        sess["user_id"] = referrer_id
        sess["csrf_token"] = "test-csrf"
    resp = client.get("/api/users/me/referral")
    assert resp.status_code == 200
    return resp.get_json()["code"]


def _activate_referred_human(client, code: str, username: str) -> sqlite3.Row:
    """Sign up a human agent through `code`, then complete profile/wallet/upload.

    Goes through the real `/signup` form (not a direct DB insert) so the
    referral code is actually consumed and validated the way a live invite
    link would be, then finishes profile, wallet and first-upload steps so
    the account reaches the same "activated" state the leaderboard counts.
    """
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
    """Register an AI agent through `code`, then complete wallet/upload.

    Mirrors `_activate_referred_human` for the agent track (`/api/register`
    instead of `/signup`, no bio/avatar PATCH step since registration
    already takes those fields) so agent-cohort activation is driven
    through the same code path a real referred agent would use.
    """
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


def _assign_badge(client, agent_name: str, badge_key: str, *, cohort_number: int = 0):
    """Award a founding badge to `agent_name` via the admin endpoint and return it.

    Uses the real admin API (with the fixture's fixed `X-Admin-Key`) rather
    than inserting a badge row directly, so these tests also cover that the
    admin-assign endpoint itself works, not just the leaderboard read side.
    """
    resp = client.post(
        "/api/admin/badges/assign",
        headers={"X-Admin-Key": "test-admin"},
        json={
            "agent_name": agent_name,
            "badge_key": badge_key,
            "cohort_number": cohort_number,
        },
    )
    assert resp.status_code == 200
    return resp.get_json()["badge"]


def test_founding_leaderboard_api_splits_tracks_and_surfaces_badges(client):
    """The leaderboard API must keep human and agent referral tracks separate.

    One referrer sponsors both a human and an agent, so this also proves
    the two cohorts don't cross-contaminate each other's slot counts,
    badge status, or bonus-progress thresholds -- a shared counter bug
    would silently under- or over-report remaining founding slots.
    """
    referrer_id = _insert_agent("captainleet", "bottube_sk_captainleet", is_human=True)
    code = _create_referral_code(client, referrer_id)

    _activate_referred_human(client, code, "humana")
    _activate_referred_human(client, code, "humanb")
    _activate_referred_human(client, code, "humanc")
    _activate_referred_agent(client, code, "agentprime")

    _assign_badge(client, "captainleet", "founding_scout_human")
    _assign_badge(client, "agentprime", "early_agent_bottube", cohort_number=1)

    resp = client.get("/api/founding/leaderboard")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["human_cohort"]["filled_slots"] == 3
    assert body["human_cohort"]["remaining_slots"] == 22
    assert body["agent_cohort"]["filled_slots"] == 1
    assert body["agent_cohort"]["remaining_slots"] == 24

    human_board = body["human_referrers"]
    assert human_board[0]["agent_name"] == "captainleet"
    assert human_board[0]["activated_referrals"] == 3
    assert human_board[0]["total_invites"] == 3
    assert human_board[0]["badges"][0]["badge_key"] == "founding_scout_human"
    assert human_board[0]["bonus_progress"][0]["threshold"] == 3
    assert human_board[0]["bonus_progress"][0]["reached"] is True

    agent_board = body["agent_sponsors"]
    assert agent_board[0]["agent_name"] == "captainleet"
    assert agent_board[0]["activated_referrals"] == 1
    assert agent_board[0]["total_invites"] == 1

    assert body["agent_cohort"]["entries"][0]["agent_name"] == "agentprime"
    assert body["agent_cohort"]["entries"][0]["badge_status"] == "awarded"
    assert body["agent_cohort"]["entries"][0]["badges"][0]["badge_key"] == "early_agent_bottube"

    assert body["pair_reservations"]["human"]["claimed"] == 3
    assert body["pair_reservations"]["agent"]["claimed"] == 1


def test_public_founding_page_renders_required_sections(client):
    """The public `/founding` HTML page must render both leaderboards and named entries.

    Checks for both the section headings and the actual activated
    usernames in the rendered HTML, so a regression that keeps the page
    structure but silently drops the server-rendered data (e.g. an empty
    template context) would still fail this test.
    """
    referrer_id = _insert_agent("humanlead", "bottube_sk_humanlead", is_human=True)
    code = _create_referral_code(client, referrer_id)

    _activate_referred_human(client, code, "alphauser")
    _activate_referred_agent(client, code, "betaagent")
    _assign_badge(client, "alphauser", "early_human_bottube", cohort_number=1)

    resp = client.get("/founding")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "BoTTube founding leaderboard" in html
    assert "Human referral leaderboard" in html
    assert "Agent sponsor leaderboard" in html
    assert "Early Human Adopters" in html
    assert "Early Agent Adopters" in html
    assert "Founding Human Pair" in html
    assert "Founding Agent Pair" in html
    assert "alphauser" in html
    assert "betaagent" in html
    assert "Early Human Adopter" in html
    assert "/signup" in html
