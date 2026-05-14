import time
import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_ban_transactions.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_ban_transactions.db")

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
from banano_blueprint import init_ban_tables

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_ban_transactions.db"
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    monkeypatch.setenv("BOTTUBE_DB", str(db_path))
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    init_ban_tables()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name):
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?)
            """,
            (agent_name, agent_name.title(), f"{agent_name}-key", time.time(), time.time()),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_ban_transaction(agent_id):
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO ban_transactions
                (agent_id, tx_type, amount_ban, reason, video_id, status, created_at)
            VALUES (?, 'reward', 1.5, 'test_reward', 'video-1', 'credited', ?)
            """,
            (agent_id, time.time()),
        )
        db.commit()


class TestBanTransactionsQueryParams:
    def test_malformed_pagination_params_return_json_400(self, client):
        agent_id = _insert_agent("ban_query_bot")
        _insert_ban_transaction(agent_id)

        assert client.get("/ban/transactions/ban_query_bot?limit=1").status_code == 200

        for query in ("limit=abc", "offset=abc", "limit=0", "offset=-1"):
            response = client.get(f"/ban/transactions/ban_query_bot?{query}")

            assert response.status_code == 400
            assert response.content_type == "application/json"
            assert response.get_json()["error"] == "Invalid pagination parameter"
