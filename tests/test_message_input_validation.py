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
    "/tmp/bottube_test_message_input_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_message_input_bootstrap.db",
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
    db_path = tmp_path / "bottube_message_input_test.db"
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


def _message_count() -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        return int(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0])


def test_send_message_accepts_documented_null_to_broadcast(client):
    _insert_agent("alice", "bottube_sk_alice")

    resp = client.post(
        "/api/messages",
        headers={"X-API-Key": "bottube_sk_alice"},
        json={"to": None, "subject": "Notice", "body": "hello agents"},
    )

    assert resp.status_code == 201
    message_id = resp.get_json()["message_id"]

    with bottube_server.app.app_context():
        row = bottube_server.get_db().execute(
            """
            SELECT from_agent, to_agent, subject, body, message_type
            FROM messages
            WHERE id = ?
            """,
            (message_id,),
        ).fetchone()

    assert row["from_agent"] == "alice"
    assert row["to_agent"] is None
    assert row["subject"] == "Notice"
    assert row["body"] == "hello agents"
    assert row["message_type"] == "general"


def test_send_message_rejects_non_string_to_without_insert(client):
    _insert_agent("alice", "bottube_sk_alice")

    resp = client.post(
        "/api/messages",
        headers={"X-API-Key": "bottube_sk_alice"},
        json={"to": {"agent": "bob"}, "body": "hello"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "to must be a string"}
    assert _message_count() == 0
