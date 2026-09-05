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

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_video_update.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_video_update.db")

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
    db_path = tmp_path / "video_update.db"
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
            VALUES ('metadata-owner', 'Metadata Owner', 'bottube_sk_metadata',
                    '', '', '', ?, ?)
            """,
            (now, now),
        )
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, description, filename, tags, created_at)
            VALUES ('metadata-video', ?, 'Original title', 'Original description',
                    'metadata-video.mp4', 'old,tag', ?)
            """,
            (int(cursor.lastrowid), now),
        )
        db.commit()
    bottube_server.app.config["TESTING"] = False
    yield bottube_server.app.test_client()


AUTH = {"X-API-Key": "bottube_sk_metadata"}


@pytest.mark.parametrize(
    "payload, expected_error",
    [
        ({"title": 42}, "title must be a string"),
        ({"description": ["not", "text"]}, "description must be a string"),
        ({"tags": ["valid", 42]}, "tags must be a string or an array of strings"),
        ({"tags": {"topic": "video"}}, "tags must be a string or an array of strings"),
    ],
)
def test_update_video_rejects_invalid_metadata_types(client, payload, expected_error):
    response = client.patch("/api/videos/metadata-video", headers=AUTH, json=payload)

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}


def test_update_video_allows_clearing_description_and_tags(client):
    response = client.patch(
        "/api/videos/metadata-video",
        headers=AUTH,
        json={"description": "", "tags": []},
    )

    assert response.status_code == 200
    assert response.get_json()["updated"] == ["description", "tags"]
    with sqlite3.connect(str(bottube_server.DB_PATH)) as db:
        row = db.execute(
            "SELECT description, tags FROM videos WHERE video_id = 'metadata-video'"
        ).fetchone()
    assert row == ("", "")


def test_update_video_reports_only_fields_actually_updated(client):
    response = client.patch(
        "/api/videos/metadata-video",
        headers=AUTH,
        json={"title": "  Better title  "},
    )

    assert response.status_code == 200
    assert response.get_json()["updated"] == ["title"]
