import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest
import werkzeug


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "test"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_bootstrap_db_path = f"/tmp/bottube_test_dashboard_analytics_{os.getpid()}.db"
os.environ.setdefault("BOTTUBE_DB_PATH", _bootstrap_db_path)
os.environ.setdefault("BOTTUBE_DB", _bootstrap_db_path)

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
    db_path = tmp_path / "bottube_dashboard_analytics.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name="dashboardcreator"):
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?)
            """,
            (agent_name, agent_name.title(), f"bottube_sk_{agent_name}", time.time(), time.time()),
        )
        db.commit()
        return int(cur.lastrowid)


def _login(client, agent_id):
    with client.session_transaction() as sess:
        sess["user_id"] = agent_id


def _insert_video(agent_id, video_id="dashdt001", created_at=None):
    if created_at is None:
        created_at = time.time()
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, category, created_at, views, likes, is_removed)
            VALUES (?, ?, ?, ?, 'education', ?, 1, 1, 0)
            """,
            (video_id, agent_id, "Dashboard datetime clip", f"{video_id}.mp4", created_at),
        )
        db.execute(
            "INSERT INTO views (video_id, ip_address, created_at) VALUES (?, ?, ?)",
            (video_id, "203.0.113.10", created_at),
        )
        db.commit()
    return video_id


def test_dashboard_analytics_routes_format_module_datetime(client):
    agent_id = _insert_agent()
    created_at = time.time()
    video_id = _insert_video(agent_id, created_at=created_at)
    _login(client, agent_id)

    analytics = client.get("/api/dashboard/analytics?days=7")
    assert analytics.status_code == 200
    data = analytics.get_json()
    assert len(data["labels"]) == 7
    assert data["series"]["views"][-1] == 1
    assert data["top_videos"][0]["video_id"] == video_id

    export = client.get("/dashboard/export.csv")
    assert export.status_code == 200
    csv_body = export.get_data(as_text=True)
    assert "Dashboard datetime clip" in csv_body
    assert "T" in csv_body
