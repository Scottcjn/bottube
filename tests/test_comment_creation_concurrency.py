"""Concurrency regressions for duplicate comment creation."""

import sqlite3
import threading

import bottube_server


def _create_comment_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE comments (
               id INTEGER PRIMARY KEY,
               video_id TEXT NOT NULL,
               agent_id INTEGER NOT NULL,
               parent_id INTEGER,
               content TEXT NOT NULL,
               comment_type TEXT NOT NULL,
               created_at REAL NOT NULL
           )"""
    )
    conn.commit()
    conn.close()


def test_concurrent_identical_comments_have_one_creator(tmp_path):
    db_path = tmp_path / "comments.db"
    _create_comment_db(db_path)
    barrier = threading.Barrier(12)
    results = []
    results_lock = threading.Lock()

    def comment(worker_id):
        conn = sqlite3.connect(db_path, timeout=15)
        barrier.wait()
        result = bottube_server._insert_comment_once(
            conn,
            video_id="video-1",
            agent_id=7,
            parent_id=None,
            content="One useful comment",
            comment_type="comment",
            created_at=1000.0 + worker_id,
        )
        conn.commit()
        conn.close()
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=comment, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, video_id, agent_id, content FROM comments"
    ).fetchall()
    conn.close()

    assert sum(created for created, _ in results) == 1
    assert len({comment_id for _, comment_id in results}) == 1
    assert len(rows) == 1
    assert rows[0][1:] == ("video-1", 7, "One useful comment")


def test_same_content_is_allowed_for_a_different_author(tmp_path):
    db_path = tmp_path / "comments.db"
    _create_comment_db(db_path)
    conn = sqlite3.connect(db_path)

    first = bottube_server._insert_comment_once(
        conn, "video-1", 7, None, "Shared thought", "comment", 1000.0
    )
    conn.commit()
    second = bottube_server._insert_comment_once(
        conn, "video-1", 8, None, "Shared thought", "comment", 1001.0
    )
    conn.commit()
    conn.close()

    assert first[0] is True
    assert second[0] is True
    assert first[1] != second[1]
