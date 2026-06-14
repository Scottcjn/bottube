"""Regression tests for Bottube #1456 — /api/feed query param validation.

The /api/feed (recommendation feed) endpoint used Flask's `type=int` coercion,
which silently falls back to the default value on parse failure (e.g.
`?page=abc` returned page=1 with HTTP 200). These tests assert the contract
returns 400 for malformed inputs and applies the documented 1-50 range.
"""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "BOTTUBE_BASE_DIR",
    "/tmp/bottube_test_1456_feed_query_validation_base",
)
os.environ.setdefault(
    "BOTTUBE_DB_PATH",
    "/tmp/bottube_test_1456_feed_query_validation.db",
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
def client(monkeypatch):
    bottube_server.app.config["TESTING"] = True
    monkeypatch.setattr(bottube_server, "_feed_imp_ensure_schema", lambda: None)

    # Bootstrap minimal schema for happy-path tests.
    base_dir = Path(os.environ["BOTTUBE_BASE_DIR"])
    base_dir.mkdir(parents=True, exist_ok=True)
    db_path = base_dir / "bottube.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY,
                agent_name TEXT,
                display_name TEXT,
                avatar_url TEXT,
                is_human INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                api_key TEXT
            );
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY,
                video_id TEXT UNIQUE,
                agent_id INTEGER,
                title TEXT,
                category TEXT,
                created_at REAL,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                dislikes INTEGER DEFAULT 0,
                thumbnail TEXT,
                is_removed INTEGER DEFAULT 0
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    yield bottube_server.app.test_client()


def test_api_feed_rejects_malformed_page_abc(client):
    resp = client.get("/api/feed?page=abc")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body == {"error": "page must be an integer"}


def test_api_feed_rejects_malformed_per_page_abc(client):
    resp = client.get("/api/feed?per_page=abc")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body == {"error": "per_page must be an integer"}


def test_api_feed_rejects_negative_page(client):
    resp = client.get("/api/feed?page=-1")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body == {"error": "page must be >= 1"}


def test_api_feed_rejects_zero_page(client):
    resp = client.get("/api/feed?page=0")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body == {"error": "page must be >= 1"}


def test_api_feed_rejects_per_page_above_max(client):
    resp = client.get("/api/feed?per_page=999999999999999")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body == {"error": "per_page must be <= 50"}


def test_api_feed_rejects_per_page_zero(client):
    resp = client.get("/api/feed?per_page=0")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body == {"error": "per_page must be >= 1"}


def test_api_feed_rejects_negative_per_page(client):
    resp = client.get("/api/feed?per_page=-1")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body == {"error": "per_page must be >= 1"}


def test_api_feed_accepts_valid_page_and_per_page(client):
    resp = client.get("/api/feed?page=1&per_page=20")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["page"] == 1
    assert "videos" in body


def test_api_feed_clamps_per_page_to_max(client):
    """The per_page max=50 contract is preserved (now via explicit check)."""
    resp = client.get("/api/feed?per_page=50")
    assert resp.status_code == 200


def test_api_feed_ignores_unrelated_query_params(client):
    """offset/since/before/sort were never read by this handler. The handler
    should not 400 on them; only the explicitly-validated page/per_page
    parameters should."""
    resp = client.get("/api/feed?offset=abc&since=abc&sort=abc&category=abc")
    assert resp.status_code == 200