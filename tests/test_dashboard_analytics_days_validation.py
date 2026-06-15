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

_bootstrap_db_path = f"/tmp/bottube_test_dash_days_{os.getpid()}.db"
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
    db_path = tmp_path / "bottube_dash_days.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name="dashdayscreator"):
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


def test_days_default_when_omitted(client):
    """No days param should fall back to the 30-day default."""
    agent_id = _insert_agent()
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["labels"]) == 30


def test_days_non_integer_returns_400(client):
    agent_id = _insert_agent()
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=abc")
    assert resp.status_code == 400
    assert "integer" in resp.get_json()["error"]


def test_days_below_minimum_returns_400(client):
    agent_id = _insert_agent()
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=6")
    assert resp.status_code == 400
    assert ">= 7" in resp.get_json()["error"]


def test_days_above_maximum_returns_400(client):
    agent_id = _insert_agent()
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=91")
    assert resp.status_code == 400
    assert "<= 90" in resp.get_json()["error"]


def test_days_at_lower_boundary(client):
    agent_id = _insert_agent()
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=7")
    assert resp.status_code == 200
    assert len(resp.get_json()["labels"]) == 7


def test_days_at_upper_boundary(client):
    agent_id = _insert_agent()
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=90")
    assert resp.status_code == 200
    assert len(resp.get_json()["labels"]) == 90


def test_days_zero_returns_400(client):
    agent_id = _insert_agent()
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=0")
    assert resp.status_code == 400


def test_days_negative_returns_400(client):
    agent_id = _insert_agent()
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=-5")
    assert resp.status_code == 400
