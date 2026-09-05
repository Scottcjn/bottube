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

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_badges_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_badges_bootstrap.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    """Redirect the hardcoded production DB path to the test bootstrap path.

    Import-time code opens `/root/bottube/bottube.db` before the `client`
    fixture can monkeypatch `DB_PATH`, so without this shim collecting this
    module would touch production badge data.
    """
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    """Force paypal_packages' schema init onto a clean test bootstrap DB.

    Removes any stale bootstrap file first so leftover badge/referral rows
    from a prior interrupted run can't inflate this run's candidate or
    cohort-number assertions.
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

    Pins `ADMIN_KEY` so badge assign/remove/candidates calls can
    authenticate without depending on whatever key the server module
    loaded from the environment.
    """
    db_path = tmp_path / "bottube_badges.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test-admin", raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("page=abc", {"error": "page must be an integer", "param": "page"}),
        ("page=0", {"error": "page must be >= 1", "param": "page"}),
        ("page=10001", {"error": "page must be <= 10000", "param": "page"}),
        ("per_page=bad", {"error": "per_page must be an integer", "param": "per_page"}),
        ("per_page=0", {"error": "per_page must be >= 1", "param": "per_page"}),
        ("per_page=101", {"error": "per_page must be <= 100", "param": "per_page"}),
    ],
)
def test_admin_badges_rejects_invalid_pagination_before_db(client, monkeypatch, query, expected):
    def unexpected_db_access():
        raise AssertionError("invalid pagination must be rejected before database access")

    monkeypatch.setattr(bottube_server, "get_db", unexpected_db_access)
    response = client.get(
        f"/api/admin/badges?{query}",
        headers={"X-Admin-Key": "test-admin"},
    )

    assert response.status_code == 400
    assert response.get_json() == expected


@pytest.mark.parametrize(("query", "page", "per_page"), [("", 1, 25), ("?page=2&per_page=1", 2, 1)])
def test_admin_badges_preserves_valid_pagination(client, query, page, per_page):
    response = client.get(
        f"/api/admin/badges{query}",
        headers={"X-Admin-Key": "test-admin"},
    )

    assert response.status_code == 200
    assert response.get_json()["page"] == page
    assert response.get_json()["per_page"] == per_page


def _insert_agent(agent_name: str, api_key: str, *, is_human: bool = False) -> int:
    """Insert a minimal agent row directly, bypassing signup/registration.

    Used for the creator/referrer seed in each test; referred accounts are
    still created through the real signup/register endpoints below, where
    the badge-candidate logic actually needs to observe them.
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

    Called right after signup/registration; a missing row means account
    creation silently failed, so asserting here turns that into an
    immediate failure instead of a confusing `NoneType` error later.
    """
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        row = db.execute("SELECT * FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
        assert row is not None
        return row


def _insert_video(agent_id: int, video_id: str, *, created_at: float = 5.0) -> None:
    """Seed a video and drive it through the referral first-upload hooks.

    Badge-candidate eligibility is derived from referral activation state,
    which only flips on a real first upload -- calling the production
    `_referral_mark_first_upload`/`_referral_refresh_invite_state` hooks
    here (instead of writing activation flags directly) keeps the test
    honest about what actually earns a candidate their badge.
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

    Writes straight into the Flask session rather than going through the
    login form -- what's under test is badge-candidate logic, not
    authentication, so this keeps the fixture setup fast and focused.
    """
    with client.session_transaction() as sess:
        sess["user_id"] = referrer_id
        sess["csrf_token"] = "test-csrf"
    resp = client.get("/api/users/me/referral")
    assert resp.status_code == 200
    return resp.get_json()["code"]


def _activate_referred_human(client, code: str, username: str) -> sqlite3.Row:
    """Sign up a human agent through `code`, then complete profile/wallet/upload.

    Goes through the real `/signup` form so the referral code is actually
    consumed and validated, then finishes profile, wallet, and first-upload
    steps so the account reaches the fully-activated state badge-candidate
    scanning looks for.
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
    instead of `/signup`) so agent-cohort badge candidates are driven
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


def test_badge_assignment_renders_on_public_surfaces_and_can_be_removed(client):
    """A badge assigned via the admin API must appear everywhere it's shown, and clear everywhere on removal.

    Walks the full surface area a founding badge touches -- the admin
    listing, the agent's own API record, their public channel page, a
    watch page for their video, and their own dashboard -- then removes
    it and re-checks the agent API. A badge that renders on some surfaces
    but not others (or that lingers after removal) would only be caught
    by exercising all of them in one pass like this.
    """
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


def test_badge_candidates_follow_referral_activation_and_scout_thresholds(client):
    """The candidates scan must surface both per-invitee and scout-bonus badges correctly.

    One referrer activates 3 humans and 1 agent: this checks each
    activated invitee gets the right badge with the right cohort/campaign
    metadata, AND that the referrer's own "founding scout" candidate
    reports the correct pair count and which bonus thresholds it crossed
    -- a miscount either way would misattribute credit for founding-cohort
    slots.
    """
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
