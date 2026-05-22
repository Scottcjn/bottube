import time


def _insert_video(video_id="watchtime01"):
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
                "watch_time_bot",
                "Watch Time Bot",
                "bottube_sk_watch_time",
                time.time(),
                time.time(),
            ),
        )
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                video_id,
                int(agent.lastrowid),
                "Watch time validation",
                f"{video_id}.mp4",
                time.time(),
            ),
        )
        db.commit()
    return video_id


def test_watch_time_rejects_missing_video(client, monkeypatch):
    import bottube_server

    class FakeCTRTracker:
        def record_watch_time(self, video_id, seconds):
            raise AssertionError("watch time should not be recorded")

    monkeypatch.setattr(
        bottube_server, "_get_ctr_tracker", lambda: FakeCTRTracker()
    )

    response = client.post(
        "/api/videos/missing-watch-time/watch_time",
        json={"seconds": 12.5},
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Video not found"}


def test_watch_time_records_existing_public_video_id(client, monkeypatch):
    import bottube_server

    video_id = _insert_video()
    recorded = []

    class FakeCTRTracker:
        def record_watch_time(self, recorded_video_id, seconds):
            recorded.append((recorded_video_id, seconds))

    monkeypatch.setattr(
        bottube_server, "_get_ctr_tracker", lambda: FakeCTRTracker()
    )

    response = client.post(
        f"/api/videos/{video_id}/watch_time",
        json={"seconds": 12.5},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["video_id"] == video_id
    assert data["seconds_recorded"] == 12.5
    assert recorded == [(video_id, 12.5)]
