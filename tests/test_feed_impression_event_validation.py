# SPDX-License-Identifier: MIT
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
    "/tmp/bottube_test_feed_impression_validation_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_feed_impression_validation_bootstrap.db",
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


def _auth_headers(api_key="bottube_sk_feed_events"):
    return {"X-API-Key": api_key}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_feed_impression_validation.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    monkeypatch.setattr(bottube_server, "_feed_imp_ensure_schema", lambda: None)
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', 0, 0, 0)
            """,
            ("feed_events_bot", "Feed Events Bot", "bottube_sk_feed_events"),
        )
        db.commit()
    yield bottube_server.app.test_client()


def test_feed_click_requires_api_key(client):
    resp = client.post("/api/feed/click", json={"imp": "imp_deadbeef"})

    assert resp.status_code == 401
    assert resp.get_json() == {"error": "Missing X-API-Key header"}


@pytest.mark.parametrize("path", ["/api/feed/click", "/api/feed/watch"])
def test_feed_impression_events_reject_non_object_json(client, path):
    headers = _auth_headers() if path == "/api/feed/click" else None
    resp = client.post(path, json=["bad"], headers=headers)

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "JSON body must be an object",
    }


@pytest.mark.parametrize("path", ["/api/feed/click", "/api/feed/watch"])
def test_feed_impression_events_reject_non_string_impression_id(client, path):
    headers = _auth_headers() if path == "/api/feed/click" else None
    resp = client.post(path, json={"imp": ["imp_bad"], "seconds": 1}, headers=headers)

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "invalid impression_id",
    }
