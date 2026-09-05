# SPDX-License-Identifier: MIT
"""Regression coverage for malformed vote request bodies."""

import time
import gc
import sqlite3
from pathlib import Path

import pytest


VIDEO_ID = "vote-json-vid"


@pytest.fixture(autouse=True)
def close_temp_sqlite_handles(app):
    """Release temp SQLite handles before Windows removes the per-test DB dir."""
    yield

    import bottube_server

    temp_root = Path(bottube_server.DB_PATH).resolve().parent
    with app.app_context():
        bottube_server.close_db(None)

    for obj in gc.get_objects():
        if not isinstance(obj, sqlite3.Connection):
            continue
        try:
            database_rows = obj.execute("PRAGMA database_list").fetchall()
        except sqlite3.Error:
            continue
        for row in database_rows:
            db_path = row[2]
            if db_path and Path(db_path).resolve().is_relative_to(temp_root):
                obj.close()
                break


def _register(client, name):
    resp = client.post(
        "/api/register",
        json={"agent_name": name, "display_name": name.replace("_", " ").title()},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


@pytest.fixture()
def vote_scenario(app, client):
    owner = _register(client, "vote_json_owner")
    voter = _register(client, "vote_json_voter")

    with app.app_context():
        import bottube_server

        db = bottube_server.get_db()
        owner_row = db.execute(
            "SELECT id FROM agents WHERE api_key = ?", (owner["api_key"],)
        ).fetchone()
        voter_row = db.execute(
            "SELECT id FROM agents WHERE api_key = ?", (voter["api_key"],)
        ).fetchone()
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (VIDEO_ID, owner_row["id"], "Vote JSON validation", "vote.mp4", time.time()),
        )
        cur = db.execute(
            """INSERT INTO comments (video_id, agent_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (VIDEO_ID, owner_row["id"], "hello vote", time.time()),
        )
        db.commit()

    return {
        "api_key": voter["api_key"],
        "voter_id": voter_row["id"],
        "comment_id": cur.lastrowid,
    }


def _auth_headers(api_key):
    return {"X-API-Key": api_key}


def _login_web_user(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["csrf_token"] = "csrf-token"
    return {"X-CSRF-Token": "csrf-token"}


def _assert_json_object_required(resp):
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert resp.get_json() == {"ok": False, "error": "JSON body must be an object"}


def _assert_bad_vote(resp):
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert resp.get_json() == {
        "error": "vote must be 1 (like), -1 (dislike), or 0 (remove)"
    }


def test_api_video_vote_rejects_non_object_json(client, vote_scenario):
    resp = client.post(
        f"/api/videos/{VIDEO_ID}/vote",
        headers=_auth_headers(vote_scenario["api_key"]),
        json=["bad"],
    )

    _assert_json_object_required(resp)


def test_api_comment_vote_rejects_bool_and_float_vote_values(client, vote_scenario):
    for payload in ({"vote": True}, {"vote": 1.0}):
        resp = client.post(
            f"/api/comments/{vote_scenario['comment_id']}/vote",
            headers=_auth_headers(vote_scenario["api_key"]),
            json=payload,
        )

        _assert_bad_vote(resp)


def test_web_video_vote_rejects_non_object_json(client, vote_scenario):
    resp = client.post(
        f"/api/videos/{VIDEO_ID}/web-vote",
        headers=_login_web_user(client, vote_scenario["voter_id"]),
        json="bad",
    )

    _assert_json_object_required(resp)


def test_web_comment_vote_rejects_bool_vote_value(client, vote_scenario):
    resp = client.post(
        f"/api/comments/{vote_scenario['comment_id']}/web-vote",
        headers=_login_web_user(client, vote_scenario["voter_id"]),
        json={"vote": True},
    )

    _assert_bad_vote(resp)


def test_integer_video_vote_still_works(client, vote_scenario):
    resp = client.post(
        f"/api/videos/{VIDEO_ID}/vote",
        headers=_auth_headers(vote_scenario["api_key"]),
        json={"vote": 1},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["likes"] == 1
    assert body["dislikes"] == 0
    assert body["your_vote"] == 1
