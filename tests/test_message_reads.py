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
    "/tmp/bottube_test_message_reads_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_message_reads_bootstrap.db",
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
    db_path = tmp_path / "bottube_message_reads_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, created_at: float) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url,
                 created_at, last_active)
            VALUES (?, ?, ?, '', '', ?, ?)
            """,
            (
                agent_name,
                agent_name.replace("-", " ").title(),
                f"bottube_sk_{agent_name}",
                created_at,
                created_at,
            ),
        )
        db.commit()
        return int(cur.lastrowid)


def _headers(agent_name: str) -> dict[str, str]:
    return {"X-API-Key": f"bottube_sk_{agent_name}"}


def _unread_count(client, agent_name: str) -> int:
    resp = client.get(
        "/api/messages/unread-count",
        headers=_headers(agent_name),
    )
    assert resp.status_code == 200
    return int(resp.get_json()["unread"])


def test_broadcast_read_state_is_per_recipient(client):
    _insert_agent("sender", 1000.0)
    _insert_agent("alice", 1001.0)
    _insert_agent("bob", 1002.0)
    create_resp = client.post(
        "/api/messages",
        headers=_headers("sender"),
        json={"subject": "Notice", "body": "Broadcast update"},
    )
    assert create_resp.status_code == 201
    message_id = create_resp.get_json()["message_id"]
    assert _unread_count(client, "alice") == 1
    assert _unread_count(client, "bob") == 1

    read_resp = client.post(
        f"/api/messages/{message_id}/read",
        headers=_headers("alice"),
    )

    assert read_resp.status_code == 200
    assert _unread_count(client, "alice") == 0
    assert _unread_count(client, "bob") == 1

    alice_inbox = client.get("/api/messages/inbox", headers=_headers("alice"))
    bob_unread = client.get(
        "/api/messages/inbox?unread_only=1",
        headers=_headers("bob"),
    )
    assert alice_inbox.status_code == 200
    assert bob_unread.status_code == 200
    assert alice_inbox.get_json()["messages"][0]["read_at"]
    assert [m["id"] for m in bob_unread.get_json()["messages"]] == [message_id]


def test_direct_message_read_state_still_uses_recipient_only(client):
    _insert_agent("sender", 1000.0)
    _insert_agent("alice", 1001.0)
    _insert_agent("bob", 1002.0)
    create_resp = client.post(
        "/api/messages",
        headers=_headers("sender"),
        json={"to": "bob", "subject": "Direct", "body": "For Bob"},
    )
    assert create_resp.status_code == 201
    message_id = create_resp.get_json()["message_id"]

    forbidden = client.post(
        f"/api/messages/{message_id}/read",
        headers=_headers("alice"),
    )
    assert forbidden.status_code == 403
    assert _unread_count(client, "bob") == 1

    read_resp = client.post(
        f"/api/messages/{message_id}/read",
        headers=_headers("bob"),
    )

    assert read_resp.status_code == 200
    assert _unread_count(client, "bob") == 0
