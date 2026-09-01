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

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_crosspost_validation.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_crosspost_validation.db")

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
    db_path = tmp_path / "crosspost.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    now = time.time()
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cursor = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio,
                 avatar_url, created_at, last_active)
            VALUES ('crosspost-owner', 'Crosspost Owner', 'bottube_sk_crosspost',
                    '', '', '', ?, ?)
            """,
            (now, now),
        )
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at)
            VALUES ('crosspost-video', ?, 'Crosspost video', 'crosspost.mp4', ?)
            """,
            (int(cursor.lastrowid), now),
        )
        db.commit()
    bottube_server.app.config["TESTING"] = False
    yield bottube_server.app.test_client()


AUTH = {"X-API-Key": "bottube_sk_crosspost"}


@pytest.mark.parametrize(
    "path,payload,expected_error",
    [
        ("/api/crosspost/moltbook", ["crosspost-video"], "JSON body must be an object"),
        ("/api/crosspost/moltbook", {"video_id": 42}, "video_id must be a string"),
        (
            "/api/crosspost/moltbook",
            {"video_id": "crosspost-video", "submolt": {"name": "agents"}},
            "submolt must be a string",
        ),
        ("/api/crosspost/x", {"video_id": ["crosspost-video"]}, "video_id must be a string"),
        (
            "/api/crosspost/x",
            {"video_id": "crosspost-video", "text": 42},
            "text must be a string",
        ),
    ],
)
def test_crosspost_routes_reject_invalid_json_types(client, path, payload, expected_error):
    response = client.post(path, headers=AUTH, json=payload)

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}


def test_moltbook_crosspost_normalizes_and_persists_valid_fields(client):
    response = client.post(
        "/api/crosspost/moltbook",
        headers=AUTH,
        json={"video_id": "  crosspost-video  ", "submolt": "  agents  "},
    )

    assert response.status_code == 200
    assert response.get_json()["submolt"] == "agents"
    with sqlite3.connect(str(bottube_server.DB_PATH)) as db:
        row = db.execute(
            "SELECT submolt_crosspost FROM videos WHERE video_id = 'crosspost-video'"
        ).fetchone()
    assert row == ("agents",)
