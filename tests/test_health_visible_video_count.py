# SPDX-License-Identifier: MIT
"""Regression: GET /health must count only publicly visible videos.

Before the fix, /health ran ``SELECT COUNT(*) FROM videos`` and so reported
removed/deleted uploads and banned agents' videos (prod reported 3,618 while
/api/videos listed 3,066). The count now uses the same public predicate as
/api/videos.
"""

import time


def _insert_video(db, video_id, agent_id, *, is_removed=0):
    db.execute(
        """INSERT INTO videos
           (video_id, agent_id, title, description, filename, category,
            views, likes, created_at, is_removed)
           VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?)""",
        (video_id, agent_id, f"Video {video_id}", "desc", f"{video_id}.mp4",
         "other", time.time(), is_removed),
    )


def test_health_video_count_matches_public_listing(client, registered_agent):
    import bottube_server

    with client.application.app_context():
        db = bottube_server.get_db()
        visible_agent = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            (registered_agent["agent_name"],),
        ).fetchone()["id"]
        db.execute(
            "INSERT INTO agents (agent_name, display_name, api_key, is_banned, created_at) "
            "VALUES ('banned_health_bot', 'Banned', 'k-banned', 1, ?)",
            (time.time(),),
        )
        banned_agent = db.execute(
            "SELECT id FROM agents WHERE agent_name = 'banned_health_bot'"
        ).fetchone()["id"]

        _insert_video(db, "vis1", visible_agent)
        _insert_video(db, "vis2", visible_agent)
        _insert_video(db, "gone1", visible_agent, is_removed=1)
        _insert_video(db, "ban1", banned_agent)
        db.commit()

    health = client.get("/health").get_json()
    listing = client.get("/api/videos?per_page=50").get_json()

    assert health["ok"] is True
    assert health["videos"] == 2
    assert health["videos"] == listing["total"]
