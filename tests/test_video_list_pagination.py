import time


def _insert_videos(count=3):
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
                "pagination_bot",
                "Pagination Bot",
                "bottube_sk_pagination",
                time.time(),
                time.time(),
            ),
        )
        agent_id = int(agent.lastrowid)
        for idx in range(count):
            video_id = f"pagevid{idx:02d}"
            db.execute(
                """
                INSERT INTO videos
                    (video_id, agent_id, title, filename, created_at,
                     is_removed)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (
                    video_id,
                    agent_id,
                    f"Pagination Video {idx}",
                    f"{video_id}.mp4",
                    time.time() + idx,
                ),
            )
        db.commit()


def test_video_list_clamps_out_of_range_page(client):
    _insert_videos(count=3)

    response = client.get("/api/videos?page=9999&per_page=2")

    assert response.status_code == 200
    data = response.get_json()
    assert data["page"] == 2
    assert data["pages"] == 2
    assert data["total"] == 3
    assert len(data["videos"]) == 1


def test_video_list_empty_result_keeps_page_one(client):
    response = client.get(
        "/api/videos?agent=no_such_agent&page=9999&per_page=2"
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["page"] == 1
    assert data["pages"] == 0
    assert data["total"] == 0
    assert data["videos"] == []
