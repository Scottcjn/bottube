# SPDX-License-Identifier: MIT
import time


def test_video_tips_returns_404_for_unknown_video(client):
    response = client.get("/api/videos/no_such_video_codex_1102/tips")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Video not found"}


def test_video_tips_returns_empty_totals_for_existing_video(app, client):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """INSERT INTO agents (agent_name, display_name, api_key, created_at)
               VALUES (?, ?, ?, ?)""",
            ("tips-owner", "Tips Owner", "tips-owner-key", time.time()),
        )
        agent_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            ("tips-owner",),
        ).fetchone()["id"]
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("tips_video_codex_1102", agent_id, "Tipless video", "tipless.mp4", time.time()),
        )
        db.commit()

    response = client.get("/api/videos/tips_video_codex_1102/tips")

    assert response.status_code == 200
    assert response.get_json() == {
        "video_id": "tips_video_codex_1102",
        "tips": [],
        "total_tips": 0,
        "total_amount": 0,
        "pending_tips": 0,
        "pending_amount": 0,
        "page": 1,
        "per_page": 10,
    }


def test_tip_leaderboard_rejects_malformed_limit(client):
    response = client.get("/api/tips/leaderboard?limit=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "limit must be an integer"}


def test_tipper_leaderboard_rejects_malformed_limit(client):
    response = client.get("/api/tips/tippers?limit=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "limit must be an integer"}


def test_tip_leaderboards_preserve_numeric_limit_bounds(client):
    response = client.get("/api/tips/leaderboard?limit=0")
    tippers = client.get("/api/tips/tippers?limit=999")

    assert response.status_code == 200
    assert response.get_json() == {"leaderboard": []}
    assert tippers.status_code == 200
    assert tippers.get_json() == {"leaderboard": []}
