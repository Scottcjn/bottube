# SPDX-License-Identifier: MIT
"""Subscriber totals must agree with the public subscriber-list contract."""

import time


def _seed_creator_and_followers(client):
    import bottube_server

    with client.application.app_context():
        db = bottube_server.get_db()
        now = time.time()
        db.executemany(
            """INSERT INTO agents
               (agent_name, api_key, display_name, is_banned, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [
                ("target_creator", "target-key", "Target Creator", 0, now),
                ("visible_follower", "visible-key", "Visible Follower", 0, now),
                ("banned_follower", "banned-key", "Banned Follower", 1, now),
            ],
        )
        ids = {
            row["agent_name"]: row["id"]
            for row in db.execute(
                """SELECT id, agent_name FROM agents
                   WHERE agent_name IN (?, ?, ?)""",
                ("target_creator", "visible_follower", "banned_follower"),
            ).fetchall()
        }
        db.executemany(
            """INSERT INTO subscriptions
               (follower_id, following_id, created_at) VALUES (?, ?, ?)""",
            [
                (ids["visible_follower"], ids["target_creator"], now),
                (ids["banned_follower"], ids["target_creator"], now),
            ],
        )
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("target-video", ids["target_creator"], "Target Video", "target.mp4", now),
        )
        db.commit()


def test_channel_and_watch_match_public_visible_subscriber_count(client):
    _seed_creator_and_followers(client)

    subscribers = client.get("/api/agents/target_creator/subscribers").get_json()
    channel_html = client.get("/agent/target_creator").get_data(as_text=True)
    watch_html = client.get("/watch/target-video").get_data(as_text=True)

    assert subscribers["count"] == 1
    assert 'id="sub-count">1</strong>' in channel_html
    assert 'id="watch-sub-count">1</span>' in watch_html


def test_creator_analytics_excludes_banned_followers_from_total_and_growth(client):
    _seed_creator_and_followers(client)

    response = client.get("/api/agents/target_creator/analytics?days=1")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["totals"]["subscribers"] == 1
    assert sum(day["new_subs"] for day in payload["subscriber_growth"]) == 1
