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

_bootstrap_db_path = f"/tmp/bottube_test_trending_pv_{os.getpid()}.db"
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
    db_path = tmp_path / "bottube_trending_pv.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _seed_video(agent_name="trendingagent"):
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            "INSERT INTO agents (agent_name, display_name, api_key, password_hash, bio, avatar_url, created_at, last_active) "
            "VALUES (?, ?, ?, '', '', '', ?, ?)",
            (agent_name, agent_name.title(), f"bottube_sk_{agent_name}", time.time(), time.time()),
        )
        agent_id = int(cur.lastrowid)
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, filename, category, created_at, views, likes, is_removed) "
            "VALUES ('tv001', ?, 'Trending test', 'tv001.mp4', 'education', ?, 5, 2, 0)",
            (agent_id, time.time()),
        )
        db.commit()
    return agent_id


def test_trending_default_limit(client):
    _seed_video()
    resp = client.get("/api/trending")
    assert resp.status_code == 200
    assert len(resp.get_json()["videos"]) <= 20


def test_trending_custom_limit(client):
    _seed_video()
    resp = client.get("/api/trending?limit=5")
    assert resp.status_code == 200


def test_trending_limit_non_integer_returns_400(client):
    resp = client.get("/api/trending?limit=abc")
    assert resp.status_code == 400
    assert "integer" in resp.get_json()["error"]


def test_trending_limit_zero_returns_400(client):
    resp = client.get("/api/trending?limit=0")
    assert resp.status_code == 400


def test_trending_limit_negative_returns_400(client):
    resp = client.get("/api/trending?limit=-5")
    assert resp.status_code == 400


def test_trending_limit_above_max_returns_400(client):
    resp = client.get("/api/trending?limit=101")
    assert resp.status_code == 400
    assert "<= 100" in resp.get_json()["error"]


def test_trending_days_non_integer_returns_400(client):
    resp = client.get("/api/trending?days=notanumber")
    assert resp.status_code == 400
    assert "days" in resp.get_json()["error"]


def test_trending_since_non_integer_returns_400(client):
    resp = client.get("/api/trending?since=abc")
    assert resp.status_code == 400
    assert "since" in resp.get_json()["error"]

def test_trending_days_negative_returns_400(client):
    resp = client.get("/api/trending?days=-5")
    assert resp.status_code == 400


def test_trending_days_zero_returns_400(client):
    resp = client.get("/api/trending?days=0")
    assert resp.status_code == 400


def test_trending_days_above_max_returns_400(client):
    resp = client.get("/api/trending?days=91")
    assert resp.status_code == 400
    assert "<= 90" in resp.get_json()["error"]


def test_trending_since_negative_returns_400(client):
    resp = client.get("/api/trending?since=-1")
    assert resp.status_code == 400


def test_trending_since_zero_returns_400(client):
    resp = client.get("/api/trending?since=0")
    assert resp.status_code == 400
