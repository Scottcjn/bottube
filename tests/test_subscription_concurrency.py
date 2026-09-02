"""Concurrency regressions for API subscription creation."""

import sqlite3
import threading

import bottube_server


def _create_subscription_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE subscriptions (
               follower_id INTEGER NOT NULL,
               following_id INTEGER NOT NULL,
               created_at REAL NOT NULL,
               PRIMARY KEY (follower_id, following_id)
           )"""
    )
    conn.commit()
    conn.close()


def test_concurrent_duplicate_subscribes_have_one_creator(tmp_path):
    db_path = tmp_path / "subscriptions.db"
    _create_subscription_db(db_path)
    barrier = threading.Barrier(12)
    results = []
    results_lock = threading.Lock()

    def subscribe(worker_id):
        conn = sqlite3.connect(db_path, timeout=15)
        barrier.wait()
        created = bottube_server._insert_subscription_once(
            conn, follower_id=7, following_id=9, created_at=1000.0 + worker_id
        )
        conn.commit()
        conn.close()
        with results_lock:
            results.append(created)

    threads = [threading.Thread(target=subscribe, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT follower_id, following_id FROM subscriptions"
    ).fetchall()
    conn.close()

    assert results.count(True) == 1
    assert results.count(False) == 11
    assert rows == [(7, 9)]


def test_existing_subscription_is_an_idempotent_non_creation(tmp_path):
    db_path = tmp_path / "subscriptions.db"
    _create_subscription_db(db_path)
    conn = sqlite3.connect(db_path)

    assert bottube_server._insert_subscription_once(conn, 7, 9, 1000.0) is True
    conn.commit()
    assert bottube_server._insert_subscription_once(conn, 7, 9, 2000.0) is False
    conn.commit()

    created_at = conn.execute(
        "SELECT created_at FROM subscriptions WHERE follower_id = 7 AND following_id = 9"
    ).fetchone()[0]
    conn.close()
    assert created_at == 1000.0
