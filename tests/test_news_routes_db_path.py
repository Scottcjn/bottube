# SPDX-License-Identifier: MIT
import sqlite3
from pathlib import Path

import news_routes


def test_news_routes_respects_bottube_base_dir(monkeypatch, tmp_path):
    db_dir = tmp_path / "instance"
    db_dir.mkdir()
    db_path = db_dir / "bottube.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, agent_name TEXT, display_name TEXT, avatar_url TEXT)")
    conn.execute("CREATE TABLE videos (video_id TEXT, title TEXT, description TEXT, created_at REAL, thumbnail TEXT, duration_sec INTEGER, views INTEGER, category TEXT, agent_id INTEGER, is_removed INTEGER)")
    conn.execute("INSERT INTO agents (id, agent_name, display_name, avatar_url) VALUES (1, 'the_daily_byte', 'Daily Byte', '')")
    conn.execute("INSERT INTO videos (video_id, title, description, created_at, thumbnail, duration_sec, views, category, agent_id, is_removed) VALUES ('vid-1', 'Hello', 'Desc', 1, 'thumb.jpg', 10, 1, 'news', 1, 0)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(news_routes, "DB_PATH", db_path)
    rows = news_routes._get_news_videos(5)
    assert len(rows) == 1
    assert rows[0]["video_id"] == "vid-1"
