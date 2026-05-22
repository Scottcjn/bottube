import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "BOTTUBE_DB_PATH",
    "/tmp/bottube_test_profile_input_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_profile_input_bootstrap.db",
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
    db_path = tmp_path / "bottube_profile_input_test.db"
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
                (agent_name, display_name, api_key, bio, avatar_url,
                 created_at, last_active)
            VALUES (?, ?, ?, '', '', ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, 1.0, 1.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _profile_row(agent_name: str):
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        return db.execute(
            """
            SELECT display_name, bio, avatar_url
            FROM agents
            WHERE agent_name = ?
            """,
            (agent_name,),
        ).fetchone()


def test_profile_update_rejects_non_object_json(client):
    _insert_agent("profilebot", "bottube_sk_profile")

    resp = client.patch(
        "/api/agents/me/profile",
        headers={"X-API-Key": "bottube_sk_profile"},
        json=["not", "an", "object"],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}


def test_profile_update_rejects_non_string_allowed_field(client):
    _insert_agent("profilebot", "bottube_sk_profile")

    resp = client.patch(
        "/api/agents/me/profile",
        headers={"X-API-Key": "bottube_sk_profile"},
        json={"display_name": ["bad"], "bio": "clean bio"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "display_name must be a string"}
    row = _profile_row("profilebot")
    assert row["bio"] == ""


def test_profile_update_still_accepts_valid_text_fields(client):
    _insert_agent("profilebot", "bottube_sk_profile")

    resp = client.patch(
        "/api/agents/me/profile",
        headers={"X-API-Key": "bottube_sk_profile"},
        json={
            "display_name": "Profile Bot",
            "bio": "Clean bio",
            "avatar_url": "https://example.com/avatar.png",
        },
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body["updated_fields"]) == {"display_name", "bio", "avatar_url"}
    row = _profile_row("profilebot")
    assert row["display_name"] == "Profile Bot"
    assert row["bio"] == "Clean bio"
    assert row["avatar_url"] == "https://example.com/avatar.png"
