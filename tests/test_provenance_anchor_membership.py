# SPDX-License-Identifier: MIT
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_anchor_membership.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_anchor_membership.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import bottube_server  # noqa: E402

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "anchor_membership.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "anchor-test-admin", raising=False)
    bottube_server._PROVENANCE_SCHEMA_READY = False
    bottube_server.init_db()
    bottube_server._ensure_provenance_schema()
    bottube_server._provenance_ensure_anchor_columns()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_claimed_batch(batch_id="batch_0123456789abcdef"):
    now = time.time()
    with sqlite3.connect(str(bottube_server.DB_PATH)) as db:
        for video_id in ("anchor-member-a", "anchor-member-b"):
            db.execute(
                """
                INSERT INTO video_provenance
                    (video_id, canonical_sha256, uploader_sig, uploaded_at,
                     anchor_batch_id, anchor_status, updated_at)
                VALUES (?, ?, ?, ?, ?, 'claimed', ?)
                """,
                (video_id, "a" * 64, "test-signature", now, batch_id, now),
            )
    return batch_id


def _callback(client, batch_id, video_ids=None, **extra):
    payload = {
        "batch_id": batch_id,
        "chain": "stub",
        "tx_hash": "b" * 64,
        "block_height": 12,
        "merkle_root": "c" * 64,
        **extra,
    }
    if video_ids is not None:
        payload["video_ids"] = video_ids
    return client.post(
        "/api/admin/provenance/anchor-result",
        headers={"X-Admin-Key": "anchor-test-admin"},
        json=payload,
    )


def test_anchor_result_rejects_mismatched_batch_membership(client):
    batch_id = _insert_claimed_batch()

    response = _callback(client, batch_id, ["anchor-member-a", "different-video"])

    assert response.status_code == 409
    assert response.get_json()["error"] == "video_ids do not match claimed batch membership"
    with sqlite3.connect(str(bottube_server.DB_PATH)) as db:
        rows = db.execute(
            "SELECT anchor_status, anchor_tx_hash FROM video_provenance ORDER BY video_id"
        ).fetchall()
    assert rows == [("claimed", ""), ("claimed", "")]


def test_anchor_result_requires_unique_video_ids_for_success(client):
    batch_id = _insert_claimed_batch()

    missing = _callback(client, batch_id)
    duplicate = _callback(client, batch_id, ["anchor-member-a", "anchor-member-a"])

    assert missing.status_code == 400
    assert duplicate.status_code == 400


def test_anchor_result_accepts_exact_batch_membership(client):
    batch_id = _insert_claimed_batch()

    response = _callback(client, batch_id, ["anchor-member-b", "anchor-member-a"])

    assert response.status_code == 200
    assert response.get_json()["rows_anchored"] == 2
    with sqlite3.connect(str(bottube_server.DB_PATH)) as db:
        rows = db.execute(
            "SELECT anchor_status, anchor_tx_hash FROM video_provenance ORDER BY video_id"
        ).fetchall()
    assert rows == [("anchored", "b" * 64), ("anchored", "b" * 64)]


def test_anchor_failure_callback_does_not_require_video_ids(client):
    batch_id = _insert_claimed_batch()

    response = _callback(client, batch_id, error="upstream anchor failed")

    assert response.status_code == 200
    assert response.get_json()["status"] == "failed"

