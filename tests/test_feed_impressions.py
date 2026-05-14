import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_feed_impressions_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_feed_impressions_bootstrap.db")
os.environ.setdefault("BOTTUBE_BASE_DIR", "/tmp")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_feed_impressions.db"
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    monkeypatch.setenv("BOTTUBE_DB", str(db_path))
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._FEED_IMP_SCHEMA_READY = False
    bottube_server.app.config["TESTING"] = True
    bottube_server.init_db()
    yield bottube_server.app.test_client()


def test_feed_click_rejects_invalid_and_missing_impressions(client):
    invalid = client.post("/api/feed/click", json={"impression_id": "not-an-imp"})
    assert invalid.status_code == 400
    assert invalid.get_json()["ok"] is False

    missing = client.post("/api/feed/click", json={"impression_id": "imp_deadbeef"})
    assert missing.status_code == 404
    assert missing.get_json() == {"ok": False, "error": "impression not found"}


def test_feed_watch_rejects_invalid_and_missing_impressions(client):
    invalid = client.post(
        "/api/feed/watch",
        json={"impression_id": "not-an-imp", "seconds": 10},
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["ok"] is False

    missing = client.post(
        "/api/feed/watch",
        json={"impression_id": "imp_deadbeef", "seconds": 10},
    )
    assert missing.status_code == 404
    assert missing.get_json() == {"ok": False, "error": "impression not found"}


def test_feed_click_and_watch_update_existing_impression(client):
    import bottube_server

    bottube_server._feed_imp_ensure_schema()
    with sqlite3.connect(str(bottube_server.DB_PATH)) as conn:
        conn.execute(
            """
            INSERT INTO feed_impressions
                (impression_id, visitor_id, surface, bucket, video_id, position, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("imp_01234567", "visitor-1", "home", "control", "video-1", 0, time.time()),
        )
        conn.commit()

    click = client.post("/api/feed/click", json={"impression_id": "imp_01234567"})
    assert click.status_code == 200
    assert click.get_json() == {"ok": True}

    watch = client.post(
        "/api/feed/watch",
        json={"impression_id": "imp_01234567", "seconds": 42},
    )
    assert watch.status_code == 200
    assert watch.get_json() == {"ok": True}

    with sqlite3.connect(str(bottube_server.DB_PATH)) as conn:
        clicked_at, watch_seconds = conn.execute(
            "SELECT clicked_at, watch_seconds FROM feed_impressions WHERE impression_id = ?",
            ("imp_01234567",),
        ).fetchone()

    assert clicked_at > 0
    assert watch_seconds == 42
