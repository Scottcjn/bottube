# SPDX-License-Identifier: MIT
import sqlite3
import time

from drama import engine
from drama import leaderboard


def make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row

    db.execute(
        """CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT UNIQUE,
            display_name TEXT,
            last_active REAL,
            drama_score REAL DEFAULT 10.0,
            drama_opt_in INTEGER DEFAULT 1
        )"""
    )
    db.execute(
        """CREATE TABLE videos (
            video_id TEXT PRIMARY KEY,
            agent_id INTEGER,
            title TEXT,
            description TEXT,
            tags TEXT DEFAULT '[]',
            views INTEGER DEFAULT 0,
            challenge_id TEXT DEFAULT '',
            created_at REAL
        )"""
    )
    db.execute(
        """CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            agent_id INTEGER,
            parent_id INTEGER,
            content TEXT,
            comment_type TEXT DEFAULT 'comment',
            created_at REAL
        )"""
    )
    db.execute(
        """CREATE TABLE tips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent_id INTEGER,
            to_agent_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'confirmed',
            created_at REAL
        )"""
    )

    now = time.time()
    agents = [
        (1, "owner", "Owner", now, 8.0, 1),
        (2, "alpha", "Alpha", now, 30.0, 1),
        (3, "beta", "Beta", now, 20.0, 1),
        (4, "gamma", "Gamma", now, 12.0, 1),
    ]
    db.executemany(
        "INSERT INTO agents (id, agent_name, display_name, last_active, drama_score, drama_opt_in) VALUES (?, ?, ?, ?, ?, ?)",
        agents,
    )

    db.execute(
        """INSERT INTO videos (video_id, agent_id, title, description, tags, views, challenge_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "vid-1",
            1,
            "Quiet render benchmark",
            "retro test clip",
            '["retro", "benchmark"]',
            12,
            "",
            now - (6 * 3600),
        ),
    )
    db.commit()
    return db


def test_needs_drama_low_engagement():
    db = make_db()
    row = db.execute(
        """SELECT v.video_id, v.agent_id, v.title, v.description, v.tags, v.created_at,
                  COALESCE(cm.comment_count, 0) AS comment_count
           FROM videos v
           LEFT JOIN (SELECT video_id, COUNT(*) AS comment_count FROM comments GROUP BY video_id) cm
           ON cm.video_id = v.video_id
           WHERE v.video_id = 'vid-1'"""
    ).fetchone()

    assert engine.needs_drama(row, now_ts=time.time(), similar_count=0) is True


def test_run_cycle_creates_events_and_comments(monkeypatch):
    db = make_db()

    monkeypatch.setattr(engine, "PROB_LEVEL1_COMMENT", 1.0)
    monkeypatch.setattr(engine, "PROB_LEVEL2_CLAPBACK", 1.0)
    monkeypatch.setattr(engine, "PROB_LEVEL3_TAGTEAM", 1.0)
    monkeypatch.setattr(engine, "PROB_LEVEL4_BROADCAST", 0.0)

    summary = engine.run_cycle(db, now_ts=time.time(), max_videos=10, seed=7)

    assert summary["scanned"] >= 1
    assert summary["triggered"] >= 1
    assert summary["events"] >= 3
    assert summary["comments"] >= 1

    event_types = {
        row["event_type"]
        for row in db.execute("SELECT event_type FROM drama_events").fetchall()
    }
    assert "challenge_sent" in event_types
    assert "roast_comment" in event_types
    assert "clapback_requested" in event_types


def test_drama_leaderboard_ranking():
    db = make_db()
    engine._ensure_schema(db)

    now = time.time()
    db.executemany(
        """INSERT INTO drama_events
           (video_id, challenger_agent_id, target_agent_id, level, event_type, response_type, rtc_tip, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("vid-1", 2, 1, 1, "roast_comment", "text", 0.0, "{}", now),
            ("vid-1", 2, 1, 2, "clapback_requested", "video", 0.0, "{}", now),
            ("vid-1", 3, 2, 1, "roast_comment", "text", 0.0, "{}", now),
        ],
    )

    db.executemany(
        "INSERT INTO tips (from_agent_id, to_agent_id, amount, status, created_at) VALUES (?, ?, ?, ?, ?)",
        [
            (1, 2, 3.0, "confirmed", now),
            (3, 2, 1.0, "confirmed", now),
        ],
    )

    db.execute(
        "INSERT INTO videos (video_id, agent_id, title, description, tags, views, challenge_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("vid-drama", 2, "clapback", "reply", "[]", 250, "drama:1", now),
    )
    db.commit()

    board = leaderboard.get_drama_leaderboard(db, limit=5)
    assert board
    assert board[0]["agent_name"] == "alpha"
    assert board[0]["score"] > board[1]["score"]
