import time


def _insert_video(video_id="viewdedupe01", views=10):
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
                "view_dedupe_bot",
                "View Dedupe Bot",
                "bottube_sk_view_dedupe",
                time.time(),
                time.time(),
            ),
        )
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, views, created_at,
                 is_removed)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                video_id,
                int(agent.lastrowid),
                "View dedupe validation",
                f"{video_id}.mp4",
                views,
                time.time(),
            ),
        )
        db.commit()
    return video_id


def _stored_views(video_id):
    import bottube_server

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        row = db.execute(
            "SELECT views FROM videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
    return int(row["views"])


def test_deduped_view_response_uses_stored_count(client, monkeypatch):
    import bottube_server

    video_id = _insert_video()

    class FakeCTRTracker:
        def record_click(self, clicked_video_id):
            assert clicked_video_id == video_id

    monkeypatch.setattr(
        bottube_server, "_get_ctr_tracker", lambda: FakeCTRTracker()
    )
    monkeypatch.setattr(
        bottube_server,
        "_view_reward_decision",
        lambda *args, **kwargs: {
            "awarded": False,
            "held": False,
            "risk_score": 0,
            "reasons": [],
        },
    )
    monkeypatch.setattr(
        bottube_server, "check_view_milestones", lambda *args, **kwargs: None
    )

    headers = {"X-Real-IP": "203.0.113.10"}
    first = client.get(f"/api/videos/{video_id}/view", headers=headers)
    second = client.get(f"/api/videos/{video_id}/view", headers=headers)

    assert first.status_code == 200
    assert first.get_json()["views"] == 11
    assert second.status_code == 200
    second_data = second.get_json()
    assert second_data["views"] == 11
    assert second_data["reward"]["reasons"] == ["deduplicated recent view"]
    assert _stored_views(video_id) == 11
