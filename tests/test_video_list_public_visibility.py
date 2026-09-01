# SPDX-License-Identifier: MIT
"""Public video listings must use the canonical visibility predicate."""

import time


def _seed_visible_and_banned_videos(client):
    import bottube_server

    with client.application.app_context():
        db = bottube_server.get_db()
        created_at = time.time()
        db.execute(
            """INSERT INTO agents
               (agent_name, api_key, display_name, is_banned, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("visible_creator", "visible-key", "Visible Creator", 0, created_at),
        )
        db.execute(
            """INSERT INTO agents
               (agent_name, api_key, display_name, is_banned, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("banned_creator", "banned-key", "Banned Creator", 1, created_at),
        )
        creators = {
            row["agent_name"]: row["id"]
            for row in db.execute(
                "SELECT id, agent_name FROM agents WHERE agent_name IN (?, ?)",
                ("visible_creator", "banned_creator"),
            ).fetchall()
        }
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, description, filename, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "visible-video",
                creators["visible_creator"],
                "Visible Video",
                "Public fixture",
                "visible.mp4",
                created_at,
            ),
        )
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, description, filename, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "banned-video",
                creators["banned_creator"],
                "Banned Video",
                "Non-public fixture",
                "banned.mp4",
                created_at + 1,
            ),
        )
        db.commit()


def test_video_list_excludes_banned_creator_from_rows_and_totals(client):
    _seed_visible_and_banned_videos(client)

    response = client.get("/api/videos?per_page=20")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 1
    assert payload["pages"] == 1
    assert [video["video_id"] for video in payload["videos"]] == ["visible-video"]


def test_video_list_agent_filter_does_not_resurface_banned_creator(client):
    _seed_visible_and_banned_videos(client)

    response = client.get("/api/videos?agent=banned_creator")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 0
    assert payload["pages"] == 0
    assert payload["videos"] == []


def test_versioned_video_list_alias_has_same_visibility(client):
    _seed_visible_and_banned_videos(client)

    response = client.get("/api/v1/videos")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 1
    assert [video["video_id"] for video in payload["videos"]] == ["visible-video"]
