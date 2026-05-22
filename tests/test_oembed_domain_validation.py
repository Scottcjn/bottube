import time


def _insert_video(video_id="oembedtest"):
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
                "oembed_bot",
                "oEmbed Bot",
                "bottube_sk_oembed",
                time.time(),
                time.time(),
            ),
        )
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, width, height,
                 created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                video_id,
                int(agent.lastrowid),
                "oEmbed domain validation",
                f"{video_id}.mp4",
                640,
                360,
                time.time(),
            ),
        )
        db.commit()
    return video_id


def test_oembed_accepts_canonical_bottube_watch_url(client):
    video_id = _insert_video()

    response = client.get(
        f"/oembed?url=https://bottube.ai/watch/{video_id}",
        base_url="https://bottube.ai",
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["provider_url"] == "https://bottube.ai"
    assert f"https://bottube.ai/embed/{video_id}" in data["html"]


def test_oembed_rejects_off_domain_watch_url(client):
    video_id = _insert_video()

    response = client.get(
        f"/oembed?url=https://evil.example/watch/{video_id}",
        base_url="https://bottube.ai",
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Invalid URL"}


def test_oembed_rejects_spoofed_bottube_host_suffix(client):
    video_id = _insert_video()

    response = client.get(
        f"/oembed?url=https://bottube.ai.evil.example/watch/{video_id}",
        base_url="https://bottube.ai",
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Invalid URL"}
