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
    "/tmp/bottube_test_claim_verify_input_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_claim_verify_input_bootstrap.db",
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
    db_path = tmp_path / "bottube_claim_verify_input_test.db"
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
                 claim_token, created_at, last_active)
            VALUES (?, ?, ?, '', '', ?, ?, ?)
            """,
            (
                agent_name,
                agent_name.title(),
                api_key,
                "claim-token",
                1.0,
                1.0,
            ),
        )
        db.commit()
        return int(cur.lastrowid)


def _claim_row(agent_name: str):
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        return db.execute(
            "SELECT x_handle, claimed FROM agents WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()


def test_claim_verify_rejects_non_object_json(client):
    _insert_agent("claimbot", "bottube_sk_claim")

    resp = client.post(
        "/api/claim/verify",
        headers={"X-API-Key": "bottube_sk_claim"},
        json=["not", "an", "object"],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    row = _claim_row("claimbot")
    assert row["claimed"] == 0


def test_claim_verify_rejects_falsy_non_object_json(client):
    _insert_agent("claimbot", "bottube_sk_claim")

    resp = client.post(
        "/api/claim/verify",
        headers={"X-API-Key": "bottube_sk_claim"},
        json=[],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    row = _claim_row("claimbot")
    assert row["claimed"] == 0


def test_claim_verify_rejects_non_string_x_handle(client):
    _insert_agent("claimbot", "bottube_sk_claim")

    resp = client.post(
        "/api/claim/verify",
        headers={"X-API-Key": "bottube_sk_claim"},
        json={"x_handle": ["bad"]},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "x_handle must be a string"}
    row = _claim_row("claimbot")
    assert row["claimed"] == 0


def test_claim_verify_null_x_handle_uses_required_validation(client):
    _insert_agent("claimbot", "bottube_sk_claim")

    resp = client.post(
        "/api/claim/verify",
        headers={"X-API-Key": "bottube_sk_claim"},
        json={"x_handle": None},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "x_handle is required"}
    row = _claim_row("claimbot")
    assert row["claimed"] == 0


def test_claim_verify_still_accepts_string_handle(client):
    _insert_agent("claimbot", "bottube_sk_claim")

    resp = client.post(
        "/api/claim/verify",
        headers={"X-API-Key": "bottube_sk_claim"},
        json={"x_handle": " @ClaimBot "},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["x_handle"] == "ClaimBot"
    row = _claim_row("claimbot")
    assert row["x_handle"] == "ClaimBot"
    assert row["claimed"] == 1
