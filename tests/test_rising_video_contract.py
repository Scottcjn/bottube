# SPDX-License-Identifier: MIT
"""Contract tests for the rising-video API and rendered page section."""

import time


def _seed_rising_videos(client):
    import bottube_server

    with client.application.app_context():
        db = bottube_server.get_db()
        now = time.time()
        db.execute(
            """INSERT INTO agents
               (agent_name, api_key, display_name, created_at)
               VALUES (?, ?, ?, ?)""",
            ("rising_creator", "rising-key", "Rising Creator", now),
        )
        agent_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", ("rising_creator",)
        ).fetchone()[0]
        videos = [
            ("fast-rising", "Fast Rising", "music", now - 7200),
            ("slow-rising", "Slow Rising", "music", now - 3600),
            ("other-rising", "Other Rising", "gaming", now - 1800),
        ]
        db.executemany(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, category, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (video_id, agent_id, title, f"{video_id}.mp4", category, created_at)
                for video_id, title, category, created_at in videos
            ],
        )
        for index in range(8):
            db.execute(
                """INSERT INTO views (video_id, ip_address, created_at)
                   VALUES (?, ?, ?)""",
                ("fast-rising", f"fast-{index}", now - 300),
            )
        db.execute(
            """INSERT INTO views (video_id, ip_address, created_at)
               VALUES (?, ?, ?)""",
            ("slow-rising", "slow-1", now - 300),
        )
        db.commit()


def test_rising_api_orders_recent_view_velocity_and_filters_category(client):
    _seed_rising_videos(client)

    response = client.get("/api/trending/rising?category=music&limit=10")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["category"] == "music"
    assert payload["window_hours"] == 24
    assert [video["video_id"] for video in payload["videos"]] == [
        "fast-rising",
        "slow-rising",
    ]
    assert payload["videos"][0]["velocity"] > payload["videos"][1]["velocity"]


def test_trending_page_populates_rising_section(client):
    _seed_rising_videos(client)

    response = client.get("/trending")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<div class="rising-section">' in html
    assert "Fast Rising" in html


def test_rising_api_rejects_invalid_limit(client):
    response = client.get("/api/trending/rising?limit=not-a-number")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "limit must be an integer",
        "param": "limit",
    }
