"""Concurrency regressions for webhook quota admission."""

import sqlite3
import threading

import bottube_server


def _create_webhook_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            secret TEXT NOT NULL,
            events TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at REAL NOT NULL
        );
        INSERT INTO webhooks (agent_id, url, secret, events, active, created_at)
        VALUES
            (7, 'https://one.example/hook', 'one', '*', 1, 1),
            (7, 'https://two.example/hook', 'two', '*', 1, 2),
            (7, 'https://three.example/hook', 'three', '*', 1, 3),
            (7, 'https://four.example/hook', 'four', '*', 1, 4);
        """
    )
    conn.commit()
    conn.close()


def _connect(path):
    return sqlite3.connect(path, timeout=15)


def test_concurrent_webhook_registration_never_exceeds_quota(tmp_path):
    db_path = tmp_path / "webhooks.db"
    _create_webhook_db(db_path)
    barrier = threading.Barrier(10)
    results = []
    errors = []
    result_lock = threading.Lock()

    def register(index):
        conn = _connect(db_path)
        barrier.wait()
        try:
            admitted = bottube_server._insert_webhook_with_quota(
                conn,
                7,
                f"https://worker-{index}.example/hook",
                f"secret-{index}",
                "*",
                10 + index,
            )
            if admitted:
                conn.commit()
            with result_lock:
                results.append(admitted)
        except Exception as exc:  # surfaced below with every worker result
            conn.rollback()
            with result_lock:
                errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=register, args=(index,)) for index in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    conn = _connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM webhooks WHERE agent_id = 7"
    ).fetchone()[0]
    conn.close()

    assert errors == []
    assert results.count(True) == 1
    assert results.count(False) == 9
    assert count == 5


def test_quota_helper_reuses_caller_owned_transaction(tmp_path):
    db_path = tmp_path / "webhooks.db"
    _create_webhook_db(db_path)
    conn = _connect(db_path)
    conn.execute("BEGIN IMMEDIATE")

    admitted = bottube_server._insert_webhook_with_quota(
        conn, 7, "https://five.example/hook", "five", "*", 5
    )

    assert admitted is True
    assert conn.in_transaction is True
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM webhooks WHERE agent_id = 7"
    ).fetchone()[0]
    conn.close()
    assert count == 5
