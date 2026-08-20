# SPDX-License-Identifier: MIT
"""Regression tests for syndication_backfill.py.

The backfill script had two identifier bugs, both fatal to its only job:

1. ``SELECT username FROM agents`` — the column is ``agent_name``. The very
   first video raised ``sqlite3.OperationalError: no such column: username``,
   so the script died before queueing anything.

2. ``vid = str(v["id"])`` — it queued the integer primary key, while
   ``syndication_queue.video_id`` holds the public ``video_id`` string
   (that is what ``syndication_poller`` enqueues and what the adapters
   resolve). Two consequences: the "already queued" check never matched, so
   every run re-queued the entire catalogue, and the rows it wrote carried an
   id downstream could not resolve.

The script is top-level code driven by ``BOTTUBE_DB_PATH``, so it is exercised
here as a subprocess against a temp DB built from the production schema.
"""

import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "syndication_backfill.py"


def _schema(name, source):
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS %s \(.*?\n\s*\);" % name, source, re.S
    )
    assert m, f"schema for {name} not found"
    return m.group(0)


@pytest.fixture()
def db_path(tmp_path):
    server = (ROOT / "bottube_server.py").read_text(encoding="utf-8", errors="replace")
    queue = (ROOT / "syndication_queue.py").read_text(encoding="utf-8", errors="replace")

    path = tmp_path / "bottube.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_schema("agents", server))
    conn.executescript(_schema("videos", server))
    # is_removed arrives via ALTER TABLE in the server's migration block
    conn.execute("ALTER TABLE videos ADD COLUMN is_removed INTEGER DEFAULT 0")
    conn.executescript(_schema("syndication_queue", queue))

    now = time.time()
    conn.execute(
        "INSERT INTO agents (id, agent_name, api_key, created_at) VALUES (1, 'alice', 'K', ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO videos (id, video_id, agent_id, title, filename, created_at) "
        "VALUES (7, 'vid_abc', 1, 'Clip', 'f.mp4', ?)",
        (now,),
    )
    conn.commit()
    conn.close()
    return path


def _run(db_path):
    env = dict(os.environ, BOTTUBE_DB_PATH=str(db_path))
    return subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True
    )


def _queue_rows(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT video_id, agent_name, video_title FROM syndication_queue"
    ).fetchall()
    conn.close()
    return rows


def test_backfill_queues_public_video_id_and_agent_name(db_path):
    result = _run(db_path)

    assert result.returncode == 0, result.stderr
    rows = _queue_rows(db_path)
    assert len(rows) == 1
    # the public string id, not the integer primary key
    assert rows[0]["video_id"] == "vid_abc"
    assert rows[0]["agent_name"] == "alice"


def test_backfill_is_idempotent(db_path):
    """A second run must queue nothing — the dedup check has to actually match."""
    assert _run(db_path).returncode == 0
    assert len(_queue_rows(db_path)) == 1

    second = _run(db_path)
    assert second.returncode == 0, second.stderr
    assert len(_queue_rows(db_path)) == 1, "re-queued a video that was already queued"
    assert "Queued 0 new videos" in second.stdout


def test_backfill_survives_missing_agent(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM agents WHERE id = 1")
    conn.commit()
    conn.close()

    result = _run(db_path)

    assert result.returncode == 0, result.stderr
    rows = _queue_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["agent_name"] == "unknown"
