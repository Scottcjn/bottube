import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_receipt_url.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_receipt_url.db")

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
    db_path = tmp_path / "bottube_receipt_url.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._PROVENANCE_SCHEMA_READY = False
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server._ensure_provenance_schema()
    bottube_server._provenance_ensure_v2_columns()
    bottube_server._provenance_ensure_v3_columns()
    bottube_server._provenance_ensure_thumb_column()
    bottube_server._provenance_ensure_anchor_columns()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_anchored_video(video_id="receiptUrl01"):
    now = time.time()
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio,
                 avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?)
            """,
            ("receipt-agent", "Receipt Agent", "bottube_sk_receipt", now, now),
        )
        agent_id = int(cur.lastrowid)
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (video_id, agent_id, "Receipt URL Test", f"{video_id}.mp4", now),
        )
        db.execute(
            """
            INSERT INTO video_provenance
                (video_id, canonical_sha256, uploader_sig, uploaded_at,
                 creator_agent_id, anchor_batch_id, anchor_tx_hash,
                 anchor_chain, anchor_block_height, anchor_manifest_hash,
                 anchor_status, anchored_at, manifest_version,
                 thumbnail_sha256, canonical_360p_sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                "a" * 64,
                "test-uploader-signature",
                now,
                agent_id,
                "receipt-url-batch",
                "tx_receipt_url_test",
                "rustchain",
                123,
                "b" * 64,
                "confirmed",
                now,
                1,
                "",
                "",
            ),
        )
        db.commit()
    return video_id


def test_video_receipt_uses_live_watch_url(client):
    video_id = _insert_anchored_video()

    response = client.get(f"/api/videos/{video_id}/receipt")

    assert response.status_code == 200
    receipt = json.loads(response.data)
    assert receipt["video"]["url"] == f"https://bottube.ai/watch/{video_id}"
    assert receipt["video"]["canonical_asset_url"] == (
        f"https://bottube.ai/api/videos/{video_id}/stream"
    )
