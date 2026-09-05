"""Concurrency regressions for view cooldown admission."""

import sqlite3
import threading

import bottube_server


def _create_view_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY,
            views INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE views (
            id INTEGER PRIMARY KEY,
            video_id TEXT NOT NULL,
            agent_id INTEGER,
            ip_address TEXT,
            created_at REAL NOT NULL
        );
        INSERT INTO videos (video_id, views) VALUES ('video-1', 0);
        """
    )
    conn.commit()
    conn.close()


def test_concurrent_same_ip_views_admit_one_event(tmp_path):
    db_path = tmp_path / "views.db"
    _create_view_db(db_path)
    barrier = threading.Barrier(12)
    results = []
    results_lock = threading.Lock()

    def record(worker_id):
        conn = sqlite3.connect(db_path, timeout=15)
        barrier.wait()
        result = bottube_server._record_view_event_once(
            conn,
            video_id="video-1",
            agent_id=worker_id,
            ip_address="203.0.113.8",
            now=1000.0,
        )
        conn.commit()
        conn.close()
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=record, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    conn = sqlite3.connect(db_path)
    event_count = conn.execute("SELECT COUNT(*) FROM views").fetchone()[0]
    stored_views = conn.execute(
        "SELECT views FROM videos WHERE video_id = 'video-1'"
    ).fetchone()[0]
    conn.close()

    assert sum(view_id is not None for view_id, _ in results) == 1
    assert {count for _, count in results} == {1}
    assert event_count == 1
    assert stored_views == 1


def test_view_is_admitted_after_cooldown_expires(tmp_path):
    db_path = tmp_path / "views.db"
    _create_view_db(db_path)
    conn = sqlite3.connect(db_path)

    first_id, first_count = bottube_server._record_view_event_once(
        conn, "video-1", 1, "203.0.113.8", now=1000.0
    )
    conn.commit()
    second_id, second_count = bottube_server._record_view_event_once(
        conn, "video-1", 1, "203.0.113.8", now=2801.0
    )
    conn.commit()
    conn.close()

    assert first_id is not None
    assert second_id is not None
    assert (first_count, second_count) == (1, 2)
