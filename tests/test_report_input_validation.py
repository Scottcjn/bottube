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
    "/tmp/bottube_test_report_input_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_report_input_bootstrap.db",
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
    db_path = tmp_path / "bottube_report_input_test.db"
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


def _insert_comment(agent_id: int, video_id: str, content: str) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, agent_id, content, 3.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _report_count() -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        return int(db.execute("SELECT COUNT(*) FROM reports").fetchone()[0])


def test_video_report_null_reason_uses_existing_invalid_reason_error(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo01A")

    resp = client.post(
        "/api/videos/ownervideo01A/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json={"reason": None},
    )

    assert resp.status_code == 400
    assert "Invalid reason" in resp.get_json()["error"]
    assert _report_count() == 0


def test_video_report_rejects_non_string_details_without_insert(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo01A")

    resp = client.post(
        "/api/videos/ownervideo01A/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json={"reason": "spam", "details": {"text": "bad"}},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "details must be a string"}
    assert _report_count() == 0


def test_comment_report_rejects_non_string_reason_without_insert(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo01A")
    comment_id = _insert_comment(owner_id, "ownervideo01A", "spammy")

    resp = client.post(
        f"/api/comments/{comment_id}/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json={"reason": ["spam"], "details": "bad comment"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "reason must be a string"}
    assert _report_count() == 0


def test_comment_report_rejects_non_object_json(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo01A")
    comment_id = _insert_comment(owner_id, "ownervideo01A", "spammy")

    resp = client.post(
        f"/api/comments/{comment_id}/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json=["not", "an", "object"],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    assert _report_count() == 0


def test_video_report_rejects_falsy_non_object_json(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo02A")

    resp = client.post(
        "/api/videos/ownervideo02A/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json=[],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    assert _report_count() == 0


def test_comment_report_rejects_falsy_non_object_json(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo03A")
    comment_id = _insert_comment(owner_id, "ownervideo03A", "spammy")

    resp = client.post(
        f"/api/comments/{comment_id}/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json=[],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    assert _report_count() == 0


def test_video_report_accepts_null_details_as_empty(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo01A")

    resp = client.post(
        "/api/videos/ownervideo01A/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json={"reason": "spam", "details": None},
    )

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert _report_count() == 1
