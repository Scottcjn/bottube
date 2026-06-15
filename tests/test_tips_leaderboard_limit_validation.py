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

_bootstrap_db_path = f"/tmp/bottube_test_tips_lb_{os.getpid()}.db"
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
    db_path = tmp_path / "bottube_tips_lb.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def test_leaderboard_limit_non_integer_returns_400(client):
    resp = client.get("/api/tips/leaderboard?limit=abc")
    assert resp.status_code == 400
    assert "integer" in resp.get_json()["error"]


def test_leaderboard_limit_zero_returns_400(client):
    resp = client.get("/api/tips/leaderboard?limit=0")
    assert resp.status_code == 400


def test_leaderboard_limit_negative_returns_400(client):
    resp = client.get("/api/tips/leaderboard?limit=-5")
    assert resp.status_code == 400


def test_leaderboard_limit_above_max_returns_400(client):
    resp = client.get("/api/tips/leaderboard?limit=51")
    assert resp.status_code == 400
    assert "<= 50" in resp.get_json()["error"]


def test_leaderboard_limit_valid_returns_200(client):
    resp = client.get("/api/tips/leaderboard?limit=10")
    assert resp.status_code == 200
    assert "leaderboard" in resp.get_json()


def test_tippers_limit_non_integer_returns_400(client):
    resp = client.get("/api/tips/tippers?limit=xyz")
    assert resp.status_code == 400
    assert "integer" in resp.get_json()["error"]


def test_tippers_limit_above_max_returns_400(client):
    resp = client.get("/api/tips/tippers?limit=100")
    assert resp.status_code == 400


def test_tippers_limit_valid_returns_200(client):
    resp = client.get("/api/tips/tippers?limit=25")
    assert resp.status_code == 200
    assert "leaderboard" in resp.get_json()
