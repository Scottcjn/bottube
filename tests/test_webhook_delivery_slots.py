"""Concurrency regressions for webhook delivery-window accounting."""

import sqlite3
import threading

import bottube_server


def _create_webhook_db(path, *, count=0, window_start=0.0):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE webhooks (
               id INTEGER PRIMARY KEY,
               active INTEGER NOT NULL,
               event_window_start REAL DEFAULT 0,
               event_count INTEGER DEFAULT 0
           )"""
    )
    conn.execute(
        "INSERT INTO webhooks (id, active, event_window_start, event_count) VALUES (1, 1, ?, ?)",
        (window_start, count),
    )
    conn.commit()
    conn.close()


def _reserve_concurrently(path, workers, *, now, limit=100):
    barrier = threading.Barrier(workers)
    results = []
    results_lock = threading.Lock()

    def reserve():
        conn = sqlite3.connect(path, timeout=15)
        barrier.wait()
        result = bottube_server._reserve_webhook_delivery_slot(
            conn, 1, now, limit=limit
        )
        conn.close()
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=reserve) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()
    return results


def _window_state(path):
    conn = sqlite3.connect(path)
    state = conn.execute(
        "SELECT event_window_start, event_count FROM webhooks WHERE id = 1"
    ).fetchone()
    conn.close()
    return state


def test_concurrent_workers_reserve_distinct_delivery_slots(tmp_path):
    db_path = tmp_path / "webhooks.db"
    _create_webhook_db(db_path, count=12, window_start=900.0)

    results = _reserve_concurrently(db_path, 16, now=1000.0)

    assert results == [True] * 16
    assert _window_state(db_path) == (900.0, 28)


def test_concurrent_workers_stop_exactly_at_window_limit(tmp_path):
    db_path = tmp_path / "webhooks.db"
    _create_webhook_db(db_path, count=97, window_start=900.0)

    results = _reserve_concurrently(db_path, 8, now=1000.0)

    assert results.count(True) == 3
    assert results.count(False) == 5
    assert _window_state(db_path) == (900.0, 100)


def test_expired_window_rolls_over_once_under_concurrency(tmp_path):
    db_path = tmp_path / "webhooks.db"
    _create_webhook_db(db_path, count=100, window_start=100.0)

    results = _reserve_concurrently(db_path, 12, now=4000.0)

    assert results == [True] * 12
    assert _window_state(db_path) == (4000.0, 12)
