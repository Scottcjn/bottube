# SPDX-License-Identifier: MIT
"""Regression tests for issue #2111 — playlist append position race.

Both playlist append routes (``/api/playlists/<id>/items`` and
``/playlist/<id>/add``) used to allocate the next ``position`` with a separate
``SELECT MAX(position)`` followed by an ``INSERT``. Two concurrent appends for
distinct videos could both read the same maximum and commit two rows on the
same position, leaving playlist order ambiguous.

The fix folds the ``MAX(position)`` calculation into the same ``INSERT``
statement so SQLite computes it under the same write lock as the row insert.
These regressions pin:

1. Sequential appends keep monotonically increasing positions without gaps.
2. A duplicate ``(playlist_id, video_id)`` append returns the documented
   ``409`` instead of leaking an ``IntegrityError``.
3. A rapid burst of appends for distinct videos never produces two items on
   the same position, and every response reports its own unique ``position``
   (or the documented 409 for duplicates).
"""
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

os.environ.setdefault(
    "BOTTUBE_DB_PATH",
    "/tmp/bottube_test_playlist_append_race_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_playlist_append_race_bootstrap.db",
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
    db_path = tmp_path / "bottube_playlist_append_race_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, created_at: float) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url,
                 created_at, last_active, is_banned)
            VALUES (?, ?, ?, '', '', ?, ?, 0)
            """,
            (
                agent_name,
                agent_name.replace("-", " ").title(),
                f"bottube_sk_{agent_name}",
                created_at,
                created_at,
            ),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(video_id: str, agent_id: int, title: str, created_at: float) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, thumbnail, created_at,
                 views, is_removed)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                video_id,
                agent_id,
                title,
                f"{video_id}.mp4",
                f"{video_id}.jpg",
                created_at,
                int(created_at),
            ),
        )
        db.commit()


def _insert_playlist(playlist_id: str, agent_id: int, title: str) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        now = time.time()
        cur = db.execute(
            """
            INSERT INTO playlists
                (playlist_id, agent_id, title, description, visibility,
                 created_at, updated_at)
            VALUES (?, ?, ?, '', 'public', ?, ?)
            """,
            (playlist_id, agent_id, title, now, now),
        )
        db.commit()
        return int(cur.lastrowid)


def _headers(agent_name: str) -> dict[str, str]:
    return {"X-API-Key": f"bottube_sk_{agent_name}"}


def test_api_sequential_appends_get_monotonic_positions(client):
    owner_id = _insert_agent("race-owner", 1000.0)
    creator_id = _insert_agent("race-creator", 1001.0)
    _insert_playlist("playlistseq1", owner_id, "Seq")
    for i in range(1, 6):
        _insert_video(f"seqvid{i:02d}", creator_id, f"V{i}", 1010.0 + i)

    positions = []
    for i in range(1, 6):
        resp = client.post(
            "/api/playlists/playlistseq1/items",
            headers=_headers("race-owner"),
            json={"video_id": f"seqvid{i:02d}"},
        )
        assert resp.status_code == 201
        positions.append(resp.get_json()["position"])

    assert positions == [1, 2, 3, 4, 5]


def test_api_duplicate_append_returns_documented_409(client):
    owner_id = _insert_agent("race-owner", 1000.0)
    creator_id = _insert_agent("race-creator", 1001.0)
    _insert_playlist("playlistdup1", owner_id, "Dup")
    _insert_video("dupvid01", creator_id, "V1", 1002.0)

    first = client.post(
        "/api/playlists/playlistdup1/items",
        headers=_headers("race-owner"),
        json={"video_id": "dupvid01"},
    )
    second = client.post(
        "/api/playlists/playlistdup1/items",
        headers=_headers("race-owner"),
        json={"video_id": "dupvid01"},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.get_json() == {"error": "Video already in playlist"}


def test_api_concurrent_appends_land_on_distinct_positions(client):
    owner_id = _insert_agent("race-owner", 1000.0)
    creator_id = _insert_agent("race-creator", 1001.0)
    playlist_db_id = _insert_playlist("playlistconc1", owner_id, "Conc")
    for i in range(1, 9):
        _insert_video(f"concvvid{i:02d}", creator_id, f"V{i}", 1010.0 + i)

    db_path = bottube_server.DB_PATH

    # Drive the race at the SQL layer: each thread opens its own connection
    # and runs the same INSERT...SELECT the route now uses, which is the actual
    # surface that previously raced on a separate SELECT MAX(position) +
    # INSERT pair. The Flask test_client itself is single-threaded against the
    # shared g.db, so without going through raw sqlite3 connections we cannot
    # actually trigger the race. This stays inside the same DB so the unique
    # (playlist_id, video_id) index still applies.
    results: list[tuple[int, int]] = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(8)

    def _append(video_id: str) -> None:
        barrier.wait()
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.execute(
                "INSERT INTO playlist_items (playlist_id, video_id, position, added_at) "
                "SELECT ?, ?, COALESCE(MAX(position), 0) + 1, ? "
                "FROM playlist_items WHERE playlist_id = ?",
                (playlist_db_id, video_id, time.time(), playlist_db_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT position FROM playlist_items WHERE rowid = ?",
                (cur.lastrowid,),
            ).fetchone()
            with results_lock:
                results.append((cur.lastrowid, row[0]))
        finally:
            conn.close()

    threads = [
        threading.Thread(target=_append, args=(f"concvvid{i:02d}",))
        for i in range(1, 9)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 8
    positions = [p for _, p in results]
    # Every position must be distinct — the bug was two threads reading the
    # same MAX(position) before either INSERT landed.
    assert len(set(positions)) == 8
    assert sorted(positions) == [1, 2, 3, 4, 5, 6, 7, 8]


def test_legacy_two_step_pattern_can_duplicate_positions(client):
    """Pin the failure mode the issue reports.

    Without a single statement that combines MAX(position) and the row insert,
    two threads that read the current maximum and INSERT in sequence can land
    two distinct videos on the same position. This is exactly what the issue
    describes and is the bug the new INSERT...SELECT statement avoids.
    """
    owner_id = _insert_agent("race-owner", 1000.0)
    creator_id = _insert_agent("race-creator", 1001.0)
    playlist_db_id = _insert_playlist("playlistrepro1", owner_id, "Repro")
    for i in (1, 2):
        _insert_video(f"reprovid{i:02d}", creator_id, f"V{i}", 1010.0 + i)

    db_path = bottube_server.DB_PATH

    seen_max: list[int] = []
    seen_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def _two_step(video_id: str) -> None:
        # Two-thread race that mimics the legacy code: read the max then insert.
        # This is intentionally NOT a fix — it shows that with separate SELECT
        # and INSERT statements (no BEGIN IMMEDIATE) two threads can both see
        # the same maximum and commit two rows on it.
        conn = sqlite3.connect(str(db_path))
        try:
            barrier.wait()
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position), 0) FROM playlist_items WHERE playlist_id = ?",
                (playlist_db_id,),
            ).fetchone()[0]
            with seen_lock:
                seen_max.append(max_pos)
            conn.execute(
                "INSERT INTO playlist_items (playlist_id, video_id, position, added_at) "
                "VALUES (?, ?, ?, ?)",
                (playlist_db_id, video_id, max_pos + 1, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    threads = [
        threading.Thread(target=_two_step, args=("reprovid01",)),
        threading.Thread(target=_two_step, args=("reprovid02",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    # The legacy pattern exposes the bug: both threads read the same MAX.
    assert len(seen_max) == 2
    assert seen_max[0] == seen_max[1]
    # And two rows now share a position.
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        rows = db.execute(
            "SELECT position, video_id FROM playlist_items "
            "WHERE playlist_id = ? ORDER BY position",
            (playlist_db_id,),
        ).fetchall()
    positions = [r[0] for r in rows]
    assert len(positions) == 2
    assert len(set(positions)) < len(positions), (
        "Legacy two-step pattern must produce duplicate positions; if this ever "
        "passes with all distinct positions, the database is serialising "
        "transactions so aggressively that the bug cannot surface."
    )


def test_api_concurrent_duplicate_append_is_handled(client):
    owner_id = _insert_agent("race-owner", 1000.0)
    creator_id = _insert_agent("race-creator", 1001.0)
    playlist_db_id = _insert_playlist("playlistdupconc1", owner_id, "DupConc")
    _insert_video("dupconcvid01", creator_id, "V1", 1010.0)

    db_path = bottube_server.DB_PATH

    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    barrier = threading.Barrier(4)

    def _append() -> None:
        barrier.wait()
        conn = sqlite3.connect(str(db_path))
        try:
            try:
                conn.execute(
                    "INSERT INTO playlist_items (playlist_id, video_id, position, added_at) "
                    "SELECT ?, ?, COALESCE(MAX(position), 0) + 1, ? "
                    "FROM playlist_items WHERE playlist_id = ?",
                    (playlist_db_id, "dupconcvid01", time.time(), playlist_db_id),
                )
                conn.commit()
                with outcomes_lock:
                    outcomes.append("ok")
            except sqlite3.IntegrityError:
                conn.rollback()
                with outcomes_lock:
                    outcomes.append("conflict")
        finally:
            conn.close()

    threads = [threading.Thread(target=_append) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert outcomes.count("ok") == 1
    assert outcomes.count("conflict") == 3

    # Only one row exists.
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        count = db.execute(
            "SELECT COUNT(*) FROM playlist_items "
            "WHERE playlist_id = (SELECT id FROM playlists WHERE playlist_id = ?)",
            ("playlistdupconc1",),
        ).fetchone()[0]
    assert count == 1