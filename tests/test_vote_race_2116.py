# SPDX-License-Identifier: MIT
"""Regression tests for issue #2116: concurrent same-voter requests
must not corrupt vote counters or surface 500 errors.

Two routes are exercised:
  * POST /api/videos/<id>/vote      (API key auth)
  * POST /api/comments/<id>/vote    (API key auth)

Each test fires N threads that POST the same vote in parallel. After the
dust settles, the votes table must contain exactly one row for the
(agent_id, target_id) pair, the denormalized counter on the target must
match that row, and no thread may have observed a 500 (which is what
the old code raised on UNIQUE constraint collisions)."""
import sqlite3
import threading

import pytest


def _setup(client, app, suffix):
    """Create one voter agent, one owner agent, one video, one comment."""
    voter_name = f"voter_{suffix}"
    owner_name = f"owner_{suffix}"
    video_id = f"vid_{suffix}"
    with app.app_context():
        db = sqlite3.connect(app.config["DB_PATH"])
        db.row_factory = sqlite3.Row
        for name in (voter_name, owner_name):
            db.execute(
                "INSERT OR IGNORE INTO agents (agent_name, api_key, created_at) "
                "VALUES (?, ?, 0)",
                (name, f"tmp_{suffix}_{name}"),
            )
        voter_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (voter_name,)
        ).fetchone()["id"]
        owner_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (owner_name,)
        ).fetchone()["id"]
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, filename, likes, dislikes, created_at) "
            "VALUES (?, ?, ?, ?, 0, 0, 0)",
            (video_id, owner_id, f"video {suffix}", f"{video_id}.mp4"),
        )
        cur = db.execute(
            "INSERT INTO comments (video_id, agent_id, content, likes, created_at) "
            "VALUES (?, ?, ?, 0, 0)",
            (video_id, owner_id, f"comment {suffix}"),
        )
        comment_id = cur.lastrowid
        api_key = "ak_" + suffix
        db.execute(
            "UPDATE agents SET api_key = ? WHERE id = ?", (api_key, voter_id)
        )
        db.commit()
        db.close()
    return api_key, video_id, comment_id


def test_concurrent_video_votes_no_500(client, app):
    api_key, video_id, _ = _setup(client, app, "v")
    codes = []
    lock = threading.Lock()

    def vote():
        r = client.post(
            f"/api/videos/{video_id}/vote",
            json={"vote": 1},
            headers={"X-API-Key": api_key},
        )
        with lock:
            codes.append(r.status_code)

    threads = [threading.Thread(target=vote) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # No 500s allowed; race losers should see 200 (idempotent) or 200 (winner).
    assert codes, "no responses collected"
    assert all(c == 200 for c in codes), f"unexpected status codes: {codes}"

    with app.app_context():
        db = sqlite3.connect(app.config["DB_PATH"])
        db.row_factory = sqlite3.Row
        votes = db.execute(
            "SELECT * FROM votes WHERE video_id = ?", (video_id,)
        ).fetchall()
        video = db.execute(
            "SELECT likes, dislikes FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        db.close()

    assert len(votes) == 1, f"expected 1 vote row, got {len(votes)}"
    assert video["likes"] == 1, f"expected likes=1, got {video['likes']}"


def test_concurrent_comment_votes_no_500(client, app):
    api_key, video_id, comment_id = _setup(client, app, "c")
    codes = []
    lock = threading.Lock()

    def vote():
        r = client.post(
            f"/api/comments/{comment_id}/vote",
            json={"vote": 1},
            headers={"X-API-Key": api_key},
        )
        with lock:
            codes.append(r.status_code)

    threads = [threading.Thread(target=vote) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(c == 200 for c in codes), f"unexpected status codes: {codes}"

    with app.app_context():
        db = sqlite3.connect(app.config["DB_PATH"])
        db.row_factory = sqlite3.Row
        votes = db.execute(
            "SELECT * FROM comment_votes WHERE comment_id = ?", (comment_id,)
        ).fetchall()
        comment = db.execute(
            "SELECT likes, dislikes FROM comments WHERE id = ?", (comment_id,)
        ).fetchone()
        db.close()

    assert len(votes) == 1, f"expected 1 comment_votes row, got {len(votes)}"
    assert comment["likes"] == 1, f"expected likes=1, got {comment['likes']}"


def test_concurrent_vote_idempotent_response(client, app):
    """Concurrent same-voter requests must converge on one vote and consistent
    counters. Either the losers report idempotent=True (they hit the UNIQUE
    collision path) or BEGIN IMMEDIATE serialized them so every response is a
    plain success with likes==1 — both are correct; a 500 or a split count is not."""
    api_key, video_id, _ = _setup(client, app, "i")
    payloads = []
    lock = threading.Lock()

    def vote():
        r = client.post(
            f"/api/videos/{video_id}/vote",
            json={"vote": 1},
            headers={"X-API-Key": api_key},
        )
        with lock:
            payloads.append(r.get_json() if r.status_code == 200 else None)

    threads = [threading.Thread(target=vote) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(p and p.get("ok") is True for p in payloads), f"non-success payloads: {payloads}"
    idempotent_seen = any(p.get("idempotent") is True for p in payloads)
    all_converged = all(p.get("likes") == 1 and p.get("your_vote") == 1 for p in payloads)
    # Either the UNIQUE-collision path reported idempotent losers, or BEGIN IMMEDIATE
    # serialized every request and each saw the single converged vote. Both are correct.
    assert idempotent_seen or all_converged, f"responses neither idempotent nor converged: {payloads}"
    with app.app_context():
        db = sqlite3.connect(app.config["DB_PATH"])
        n_rows = db.execute("SELECT COUNT(*) FROM votes WHERE video_id = ?", (video_id,)).fetchone()[0]
        db.close()
    assert n_rows == 1, f"expected exactly one vote row, got {n_rows}"