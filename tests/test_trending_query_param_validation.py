# SPDX-License-Identifier: MIT
"""Regression coverage for /api/trending query parameter validation."""

import time


def _insert_trending_video(video_id, *, views=1, likes=1, category="other"):
    import bottube_server

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        agent = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio,
                 avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', 0, ?, ?)
            """,
            (
                f"{video_id}_agent",
                f"{video_id} Agent",
                f"bottube_sk_{video_id}",
                time.time(),
                time.time(),
            ),
        )
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, category, created_at,
                 views, likes, is_removed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                video_id,
                int(agent.lastrowid),
                f"{video_id} title",
                f"{video_id}.mp4",
                category,
                time.time(),
                views,
                likes,
            ),
        )
        db.commit()


def test_trending_rejects_non_integer_limit(client):
    response = client.get("/api/trending?limit=not-an-int")

    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]
    assert "integer" in data["error"]


def test_trending_rejects_zero_limit(client):
    response = client.get("/api/trending?limit=0")

    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]
    assert ">= 1" in data["error"]


def test_trending_rejects_limit_above_max(client):
    response = client.get("/api/trending?limit=51")

    assert response.status_code == 400
    data = response.get_json()
    assert "limit" in data["error"]
    assert "<= 50" in data["error"]


def test_trending_accepts_limit_boundary(client):
    _insert_trending_video("trendlimit01")

    response = client.get("/api/trending?limit=1")

    assert response.status_code == 200
    data = response.get_json()
    assert data["limit"] == 1
    assert len(data["videos"]) <= 1
