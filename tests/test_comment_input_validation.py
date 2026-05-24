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
    "/tmp/bottube_test_comment_input_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_comment_input_bootstrap.db",
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
    db_path = tmp_path / "bottube_comment_input_test.db"
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


def _insert_video(agent_id: int, video_id: str) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, f"Video {video_id}", f"{video_id}.mp4", 2.0),
        )
        db.commit()


def _comment_count() -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        return int(db.execute("SELECT COUNT(*) FROM comments").fetchone()[0])


def test_api_comment_null_content_returns_validation_error(client):
    commenter_id = _insert_agent("alice", "bottube_sk_alice")
    _insert_video(commenter_id, "alicevideo01A")

    resp = client.post(
        "/api/videos/alicevideo01A/comment",
        headers={"X-API-Key": "bottube_sk_alice"},
        json={"content": None},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "content is required"}
    assert _comment_count() == 0


def test_api_comment_rejects_non_string_comment_type_without_insert(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("alice", "bottube_sk_alice")
    _insert_video(owner_id, "ownervideo01A")

    resp = client.post(
        "/api/videos/ownervideo01A/comment",
        headers={"X-API-Key": "bottube_sk_alice"},
        json={"content": "good video", "comment_type": ["review"]},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "comment_type must be a string"}
    assert _comment_count() == 0


def test_api_comment_accepts_null_comment_type_as_default(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("alice", "bottube_sk_alice")
    _insert_video(owner_id, "ownervideo01A")

    resp = client.post(
        "/api/videos/ownervideo01A/comment",
        headers={"X-API-Key": "bottube_sk_alice"},
        json={"content": "good video", "comment_type": None},
    )

    assert resp.status_code == 201
    assert resp.get_json()["comment_type"] == "comment"


def test_api_comment_rejects_falsy_non_object_json(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("alice", "bottube_sk_alice")
    _insert_video(owner_id, "ownervideo02A")

    resp = client.post(
        "/api/videos/ownervideo02A/comment",
        headers={"X-API-Key": "bottube_sk_alice"},
        json=[],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    assert _comment_count() == 0


def test_web_comment_rejects_non_object_json(client):
    user_id = _insert_agent("webalice", "bottube_sk_webalice")
    _insert_video(user_id, "webvideo01A")

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "test-csrf"

    resp = client.post(
        "/api/videos/webvideo01A/web-comment",
        headers={"X-CSRF-Token": "test-csrf"},
        json=["not", "an", "object"],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    assert _comment_count() == 0


def test_web_comment_rejects_falsy_non_object_json(client):
    user_id = _insert_agent("webbob", "bottube_sk_webbob")
    _insert_video(user_id, "webvideo02A")

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "test-csrf"

    resp = client.post(
        "/api/videos/webvideo02A/web-comment",
        headers={"X-CSRF-Token": "test-csrf"},
        json=[],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    assert _comment_count() == 0
