"""Concurrency regressions for one-time quest rewards."""

import sqlite3
import threading

import bottube_server


def _create_quest_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            bio TEXT DEFAULT '',
            avatar_url TEXT DEFAULT '',
            rtc_balance REAL DEFAULT 0
        );
        CREATE TABLE quests (
            quest_key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'onboarding',
            reward_rtc REAL DEFAULT 0,
            goal_count INTEGER DEFAULT 1,
            metric_key TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE agent_quests (
            agent_id INTEGER NOT NULL,
            quest_key TEXT NOT NULL,
            progress_count INTEGER DEFAULT 0,
            completed_at REAL DEFAULT 0,
            rewarded_at REAL DEFAULT 0,
            last_event_at REAL DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            PRIMARY KEY (agent_id, quest_key)
        );
        CREATE TABLE earnings (
            id INTEGER PRIMARY KEY,
            agent_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            reason TEXT NOT NULL,
            video_id TEXT DEFAULT '',
            created_at REAL NOT NULL
        );
        INSERT INTO agents (id, bio, avatar_url, rtc_balance)
        VALUES (7, 'Complete profile', '/avatars/7.png', 0);
        INSERT INTO quests
            (quest_key, title, description, category, reward_rtc,
             goal_count, metric_key, is_active, sort_order)
        VALUES
            ('profile_complete', 'Profile', '', 'onboarding', 5,
             1, 'profile_complete', 1, 1);
        """
    )
    conn.commit()
    conn.close()


def _connect(path):
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def test_concurrent_first_refresh_awards_quest_once(tmp_path):
    db_path = tmp_path / "quests.db"
    _create_quest_db(db_path)
    barrier = threading.Barrier(10)
    errors = []
    errors_lock = threading.Lock()

    def refresh():
        conn = _connect(db_path)
        barrier.wait()
        try:
            snapshots = bottube_server._refresh_agent_quests(
                conn, 7, ["profile_complete"]
            )
            conn.commit()
            assert snapshots[0]["rewarded_at"] > 0
        except Exception as exc:  # surfaced below with all worker context
            conn.rollback()
            with errors_lock:
                errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=refresh) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    conn = _connect(db_path)
    progress_rows = conn.execute("SELECT COUNT(*) FROM agent_quests").fetchone()[0]
    earning_rows = conn.execute(
        "SELECT COUNT(*) FROM earnings WHERE reason = 'quest_complete:profile_complete'"
    ).fetchone()[0]
    balance = conn.execute("SELECT rtc_balance FROM agents WHERE id = 7").fetchone()[0]
    conn.close()

    assert errors == []
    assert progress_rows == 1
    assert earning_rows == 1
    assert balance == 5


def test_refresh_reuses_caller_owned_write_transaction(tmp_path):
    db_path = tmp_path / "quests.db"
    _create_quest_db(db_path)
    conn = _connect(db_path)
    conn.execute("BEGIN IMMEDIATE")

    snapshots = bottube_server._refresh_agent_quests(
        conn, 7, ["profile_complete"]
    )
    conn.commit()
    conn.close()

    assert snapshots[0]["completed"] is True
    assert snapshots[0]["rewarded_at"] > 0
