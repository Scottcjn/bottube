# SPDX-License-Identifier: MIT
"""Regression tests: mood writes must be authorized, not merely authenticated.

``require_api_key`` proves the caller holds *a* valid key and stashes the row on
``g.agent``. It never inspects the ``agent_name`` in the URL. The mood write
handlers then re-resolved the target agent straight from that URL and ignored
``g.agent`` entirely -- so any agent could register a free account and drive any
other agent's mood (an IDOR / horizontal privilege escalation).

PR #1639 closed the *anonymous* case by adding the decorator. These tests cover
what the decorator cannot: that the authenticated caller actually owns the agent
it is writing to.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Importing bottube_server runs module-level table bootstraps (e.g.
# gemini_blueprint.init_gemini_tables) that fall back to the *production* DB
# path when BOTTUBE_DB is unset. Point them at a scratch file before import so
# this module is self-sufficient and does not depend on a writable /root.
_BOOTSTRAP_DB = os.path.join(
    tempfile.gettempdir(), "bottube_test_mood_write_authorization_bootstrap.db"
)
os.environ.setdefault("BOTTUBE_DB", _BOOTSTRAP_DB)
os.environ.setdefault("BOTTUBE_DB_PATH", _BOOTSTRAP_DB)

import bottube_server  # noqa: E402


pytestmark = pytest.mark.skipif(
    not bottube_server.MOOD_ENGINE_AVAILABLE,
    reason="mood engine not importable; mood routes short-circuit to 503",
)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """A test client backed by a fresh temp database."""
    db_path = tmp_path / "bottube_mood_authz.db"
    video_dir = tmp_path / "videos"
    thumb_dir = tmp_path / "thumbnails"
    avatar_dir = tmp_path / "avatars"
    for d in (video_dir, thumb_dir, avatar_dir):
        d.mkdir()

    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "VIDEO_DIR", video_dir, raising=False)
    monkeypatch.setattr(bottube_server, "THUMB_DIR", thumb_dir, raising=False)
    monkeypatch.setattr(bottube_server, "AVATAR_DIR", avatar_dir, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0

    with bottube_server.app.app_context():
        bottube_server.init_db()

    bottube_server.app.config["TESTING"] = True
    return bottube_server.app.test_client()


def _register(client, name):
    resp = client.post("/api/register", json={
        "agent_name": name,
        "display_name": name,
        "bio": f"test agent {name}",
    })
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


@pytest.fixture()
def victim(client):
    return _register(client, "mood_victim_bot")


@pytest.fixture()
def attacker(client):
    return _register(client, "mood_attacker_bot")


# --- the hole PR #1639 did NOT close -------------------------------------


def test_mood_update_rejects_non_owning_key(client, victim, attacker):
    """A valid key belonging to a *different* agent must not move my mood."""
    resp = client.post(
        f"/api/v1/agents/{victim['agent_name']}/mood/update",
        json={"force_state": "frustrated", "trigger_reason": "pwned"},
        headers={"X-API-Key": attacker["api_key"]},
    )
    assert resp.status_code == 403, resp.get_json()


def test_mood_signal_rejects_non_owning_key(client, victim, attacker):
    """The signal endpoint is a write too, and needs the same ownership check."""
    resp = client.post(
        f"/api/v1/agents/{victim['agent_name']}/mood/signal",
        json={"signal_type": "comment_sentiment", "signal_value": -100},
        headers={"X-API-Key": attacker["api_key"]},
    )
    assert resp.status_code == 403, resp.get_json()


def test_mood_update_by_non_owner_does_not_change_state(client, victim, attacker):
    """A rejected write must be a no-op, not a rejected-but-applied write."""
    before = client.get(f"/api/v1/agents/{victim['agent_name']}/mood").get_json()

    client.post(
        f"/api/v1/agents/{victim['agent_name']}/mood/update",
        json={"force_state": "frustrated", "trigger_reason": "pwned"},
        headers={"X-API-Key": attacker["api_key"]},
    )

    after = client.get(f"/api/v1/agents/{victim['agent_name']}/mood").get_json()
    assert after.get("current_mood") == before.get("current_mood")


# --- what must keep working ---------------------------------------------


def test_owner_can_still_update_own_mood(client, victim):
    """Control: the legitimate self-service path is unaffected."""
    resp = client.post(
        f"/api/v1/agents/{victim['agent_name']}/mood/update",
        json={"force_state": "energetic", "trigger_reason": "self-service"},
        headers={"X-API-Key": victim["api_key"]},
    )
    assert resp.status_code == 200, resp.get_json()


def test_owner_can_still_record_own_signal(client, victim):
    """Control: the legitimate signal path is unaffected."""
    resp = client.post(
        f"/api/v1/agents/{victim['agent_name']}/mood/signal",
        json={"signal_type": "view_count", "signal_value": 42},
        headers={"X-API-Key": victim["api_key"]},
    )
    assert resp.status_code == 200, resp.get_json()


# --- regressions on PR #1639's own fix ----------------------------------


def test_mood_update_still_requires_a_key(client, victim):
    """Anonymous writes stay closed (the hole PR #1639 fixed)."""
    resp = client.post(
        f"/api/v1/agents/{victim['agent_name']}/mood/update",
        json={"force_state": "frustrated"},
    )
    assert resp.status_code == 401, resp.get_json()


def test_mood_signal_still_requires_a_key(client, victim):
    resp = client.post(
        f"/api/v1/agents/{victim['agent_name']}/mood/signal",
        json={"signal_type": "view_count", "signal_value": 1},
    )
    assert resp.status_code == 401, resp.get_json()


def test_unknown_agent_is_404_not_403(client, attacker):
    """A missing target is still reported as missing for an authenticated caller."""
    resp = client.post(
        "/api/v1/agents/no_such_agent_at_all/mood/update",
        json={"force_state": "playful"},
        headers={"X-API-Key": attacker["api_key"]},
    )
    assert resp.status_code == 404, resp.get_json()
