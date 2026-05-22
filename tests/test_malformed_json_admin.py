"""Tests for malformed JSON validation on admin referral and badge endpoints.

Reproduces the crash scenarios described in GitHub issue #1212 where malformed
JSON bodies could hit .get()/.strip() on non-object or non-string values before
reaching the normal 400-class validation path.
"""

import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_malformed_json.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_malformed_json.db")

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
    db_path = tmp_path / "bottube_malformed.db"
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


ADMIN_HEADERS = {"X-Admin-Key": "test-admin"}


class TestReferralReviewMalformedJSON:
    """POST /api/admin/referrals/<id>/review with bad JSON shapes."""

    def _seed_referral(self, client):
        """Create a referral invite we can review."""
        referrer_id = _insert_agent("malref", "sk_malref", is_human=True)
        with client.session_transaction() as sess:
            sess["user_id"] = referrer_id
            sess["csrf_token"] = "test-csrf"
        code = client.get("/api/users/me/referral").get_json()["code"]
        reg = client.post(
            "/api/register",
            json={
                "agent_name": "malreviewbot",
                "display_name": "MalReview Bot",
                "bio": "test",
                "avatar_url": "https://example.com/mal.jpg",
                "ref_code": code,
            },
        )
        assert reg.status_code == 201
        admin_resp = client.get("/api/admin/referrals", headers=ADMIN_HEADERS)
        return admin_resp.get_json()["referrals"][0]["id"]

    def test_array_body_returns_400(self, client):
        invite_id = self._seed_referral(client)
        resp = client.post(
            f"/api/admin/referrals/{invite_id}/review",
            headers=ADMIN_HEADERS,
            json=["not", "an", "object"],
        )
        assert resp.status_code == 400
        assert "JSON object required" in resp.get_json()["error"]

    def test_action_is_list_returns_400(self, client):
        invite_id = self._seed_referral(client)
        resp = client.post(
            f"/api/admin/referrals/{invite_id}/review",
            headers=ADMIN_HEADERS,
            json={"action": ["approve"]},
        )
        assert resp.status_code == 400
        assert "action must be a string" in resp.get_json()["error"]

    def test_note_is_dict_returns_400(self, client):
        invite_id = self._seed_referral(client)
        resp = client.post(
            f"/api/admin/referrals/{invite_id}/review",
            headers=ADMIN_HEADERS,
            json={"action": "approve", "note": {"text": "nested"}},
        )
        assert resp.status_code == 400
        assert "note must be a string" in resp.get_json()["error"]

    def test_valid_review_still_works(self, client):
        invite_id = self._seed_referral(client)
        resp = client.post(
            f"/api/admin/referrals/{invite_id}/review",
            headers=ADMIN_HEADERS,
            json={"action": "approve", "note": "looks good"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["review_status"] == "approved"


class TestBadgeAssignMalformedJSON:
    """POST /api/admin/badges/assign with bad JSON shapes."""

    def _seed_agent(self, client):
        return _insert_agent("badgeguy", "sk_badgeguy", is_human=True)

    def test_array_body_returns_400(self, client):
        agent_id = self._seed_agent(client)
        resp = client.post(
            "/api/admin/badges/assign",
            headers=ADMIN_HEADERS,
            json=["not", "an", "object"],
        )
        assert resp.status_code == 400
        assert "JSON object required" in resp.get_json()["error"]

    def test_badge_key_is_list_returns_400(self, client):
        self._seed_agent(client)
        resp = client.post(
            "/api/admin/badges/assign",
            headers=ADMIN_HEADERS,
            json={
                "agent_name": "badgeguy",
                "badge_key": ["early_human_bottube"],
            },
        )
        assert resp.status_code == 400
        assert "badge_key must be a string" in resp.get_json()["error"]

    def test_valid_assign_still_works(self, client):
        self._seed_agent(client)
        resp = client.post(
            "/api/admin/badges/assign",
            headers=ADMIN_HEADERS,
            json={
                "agent_name": "badgeguy",
                "badge_key": "early_human_bottube",
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["badge"]["badge_key"] == "early_human_bottube"


class TestBadgeRemoveMalformedJSON:
    """POST /api/admin/badges/<id>/remove with bad JSON shapes."""

    def _seed_badge(self, client):
        agent_id = _insert_agent("removeguy", "sk_removeguy", is_human=True)
        assign = client.post(
            "/api/admin/badges/assign",
            headers=ADMIN_HEADERS,
            json={
                "agent_name": "removeguy",
                "badge_key": "early_human_bottube",
            },
        )
        assert assign.status_code == 200
        return assign.get_json()["badge"]["id"]

    def test_array_body_returns_400(self, client):
        badge_id = self._seed_badge(client)
        resp = client.post(
            f"/api/admin/badges/{badge_id}/remove",
            headers=ADMIN_HEADERS,
            json=["not", "an", "object"],
        )
        assert resp.status_code == 400
        assert "JSON object required" in resp.get_json()["error"]

    def test_removed_by_is_dict_returns_400(self, client):
        badge_id = self._seed_badge(client)
        resp = client.post(
            f"/api/admin/badges/{badge_id}/remove",
            headers=ADMIN_HEADERS,
            json={"removed_by": {"name": "reviewer"}},
        )
        assert resp.status_code == 400
        assert "removed_by must be a string" in resp.get_json()["error"]

    def test_valid_remove_still_works(self, client):
        badge_id = self._seed_badge(client)
        resp = client.post(
            f"/api/admin/badges/{badge_id}/remove",
            headers=ADMIN_HEADERS,
            json={"removed_by": "reviewer"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["badge"]["is_active"] is False
