# SPDX-License-Identifier: MIT
"""GET /api/agents/me/playlists and private GET /api/playlists/<id> must honour X-API-Key."""
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "BOTTUBE_DB_PATH",
    "/tmp/bottube_test_playlist_api_key_viewer_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_playlist_api_key_viewer_bootstrap.db",
)

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages  # noqa: E402


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server  # noqa: E402

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_playlist_api_key_viewer_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name, *, is_banned=0):
    now = time.time()
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """INSERT INTO agents
                   (agent_name, display_name, api_key, bio, avatar_url,
                    created_at, last_active, is_banned)
               VALUES (?, ?, ?, '', '', ?, ?, ?)""",
            (agent_name, agent_name, f"bottube_sk_{agent_name}", now, now, is_banned),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_playlist(playlist_id, agent_id, visibility):
    now = time.time()
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            "INSERT INTO playlists (playlist_id, agent_id, title, description, "
            "visibility, created_at, updated_at) VALUES (?, ?, ?, '', ?, ?, ?)",
            (playlist_id, agent_id, f"title-{playlist_id}", visibility, now, now),
        )
        db.commit()


def _key(name):
    return {"X-API-Key": f"bottube_sk_{name}"}


def test_my_playlists_accepts_api_key(client):
    """Documented as 'Requires X-API-Key' and called that way by both SDKs."""
    owner = _insert_agent("pl-owner")
    _insert_playlist("plpub", owner, "public")
    _insert_playlist("plpriv", owner, "private")

    resp = client.get("/api/agents/me/playlists", headers=_key("pl-owner"))

    assert resp.status_code == 200, resp.get_json()
    ids = {p["playlist_id"] for p in resp.get_json()["playlists"]}
    assert ids == {"plpub", "plpriv"}


def test_my_playlists_rejects_missing_invalid_or_banned_key(client):
    _insert_agent("pl-banned", is_banned=1)

    assert client.get("/api/agents/me/playlists").status_code == 401
    assert client.get(
        "/api/agents/me/playlists", headers={"X-API-Key": "bottube_sk_nope"}
    ).status_code == 401
    assert client.get(
        "/api/agents/me/playlists", headers=_key("pl-banned")
    ).status_code == 401


def test_owner_can_read_own_private_playlist_with_api_key(client):
    owner = _insert_agent("pl-owner2")
    _insert_agent("pl-other")
    _insert_playlist("plsecret", owner, "private")

    ok = client.get("/api/playlists/plsecret", headers=_key("pl-owner2"))
    other = client.get("/api/playlists/plsecret", headers=_key("pl-other"))
    anon = client.get("/api/playlists/plsecret")

    assert ok.status_code == 200, ok.get_json()
    assert ok.get_json()["playlist_id"] == "plsecret"
    assert other.status_code == 404
    assert anon.status_code == 404


def test_agent_playlist_listing_shows_private_to_api_key_owner(client):
    owner = _insert_agent("pl-owner3")
    _insert_agent("pl-viewer3")
    _insert_playlist("plpub3", owner, "public")
    _insert_playlist("plpriv3", owner, "private")

    def ids(headers):
        resp = client.get("/api/agents/pl-owner3/playlists", headers=headers)
        assert resp.status_code == 200
        return {p["playlist_id"] for p in resp.get_json()["playlists"]}

    assert ids(_key("pl-owner3")) == {"plpub3", "plpriv3"}
    assert ids(_key("pl-viewer3")) == {"plpub3"}
    assert ids({}) == {"plpub3"}


def test_agent_profile_private_fields_only_for_api_key_owner(client):
    _insert_agent("pl-owner4")
    _insert_agent("pl-viewer4")

    own = client.get("/api/agents/pl-owner4", headers=_key("pl-owner4")).get_json()
    other = client.get("/api/agents/pl-owner4", headers=_key("pl-viewer4")).get_json()
    anon = client.get("/api/agents/pl-owner4").get_json()

    assert "rtc_balance" in own["agent"]
    assert "rtc_balance" not in other["agent"]
    assert "rtc_balance" not in anon["agent"]
