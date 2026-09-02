# SPDX-License-Identifier: MIT
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_vote_concurrency_bootstrap.db")

import bottube_server  # noqa: E402


@pytest.fixture()
def vote_db(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_vote_concurrency.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        owner = db.execute(
            """INSERT INTO agents
                   (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
               VALUES ('owner', 'Owner', 'bottube_sk_owner', '', '', ?, ?)""",
            (time.time(), time.time()),
        ).lastrowid
        voter = db.execute(
            """INSERT INTO agents
                   (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
               VALUES ('voter', 'Voter', 'bottube_sk_voter', '', '', ?, ?)""",
            (time.time(), time.time()),
        ).lastrowid
        db.execute(
            """INSERT INTO videos (video_id, agent_id, title, filename, created_at)
               VALUES ('vote-race-video', ?, 'Vote race', 'vote-race.mp4', ?)""",
            (owner, time.time()),
        )
        comment_id = db.execute(
            """INSERT INTO comments (video_id, agent_id, content, created_at)
               VALUES ('vote-race-video', ?, 'Vote race comment', ?)""",
            (owner, time.time()),
        ).lastrowid
        db.commit()

    return db_path, int(voter), int(comment_id)


def _exercise_two_simultaneous_votes(monkeypatch, db_path, route):
    real_connect = sqlite3.connect
    read_barrier = threading.Barrier(2)
    start_barrier = threading.Barrier(2)
    errors = []
    statuses = []

    class BarrierConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            normalized = " ".join(sql.split()).lower()
            if normalized.startswith("select vote from votes where") or normalized.startswith(
                "select vote from comment_votes where"
            ):
                try:
                    read_barrier.wait(timeout=0.25)
                except threading.BrokenBarrierError:
                    pass
            return super().execute(sql, parameters)

    def connect_with_barrier(*args, **kwargs):
        kwargs["factory"] = BarrierConnection
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(bottube_server.sqlite3, "connect", connect_with_barrier)

    def send_vote():
        try:
            with bottube_server.app.test_client() as client:
                start_barrier.wait(timeout=2)
                response = client.post(
                    route,
                    headers={"X-API-Key": "bottube_sk_voter"},
                    json={"vote": -1},
                )
                statuses.append(response.status_code)
        except Exception as exc:  # pragma: no cover - assertion reports the exception
            errors.append(exc)

    threads = [threading.Thread(target=send_vote) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(statuses) == [200, 200]

    return real_connect


def test_concurrent_same_voter_video_requests_are_idempotent(monkeypatch, vote_db):
    db_path, voter_id, _ = vote_db
    real_connect = _exercise_two_simultaneous_votes(
        monkeypatch,
        db_path,
        "/api/videos/vote-race-video/vote",
    )

    with real_connect(db_path) as db:
        assert db.execute(
            "SELECT vote FROM votes WHERE agent_id = ? AND video_id = 'vote-race-video'",
            (voter_id,),
        ).fetchall() == [(-1,)]
        assert db.execute(
            "SELECT likes, dislikes FROM videos WHERE video_id = 'vote-race-video'"
        ).fetchone() == (0, 1)


def test_concurrent_same_voter_comment_requests_are_idempotent(monkeypatch, vote_db):
    db_path, voter_id, comment_id = vote_db
    real_connect = _exercise_two_simultaneous_votes(
        monkeypatch,
        db_path,
        f"/api/comments/{comment_id}/vote",
    )

    with real_connect(db_path) as db:
        assert db.execute(
            "SELECT vote FROM comment_votes WHERE agent_id = ? AND comment_id = ?",
            (voter_id, comment_id),
        ).fetchall() == [(-1,)]
        assert db.execute(
            "SELECT likes, dislikes FROM comments WHERE id = ?",
            (comment_id,),
        ).fetchone() == (0, 1)
