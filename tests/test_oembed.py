import time


def _insert_oembed_video(client, video_id="oembed123"):
    import bottube_server

    with client.application.app_context():
        db = bottube_server.get_db()
        agent_cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', 0, ?, ?)
            """,
            ("previewbot", "Preview Bot", "bottube_sk_previewbot", time.time(), time.time()),
        )
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, description, filename, thumbnail, width, height, duration_sec, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                video_id,
                int(agent_cur.lastrowid),
                "Preview Demo",
                "Short clip for rich preview tests",
                f"{video_id}.mp4",
                f"{video_id}.jpg",
                720,
                720,
                8.0,
                time.time(),
            ),
        )
        db.commit()
    return video_id


def test_oembed_returns_video_payload(client):
    video_id = _insert_oembed_video(client)

    resp = client.get(f"/oembed?url=https://bottube.ai/watch/{video_id}&format=json")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["version"] == "1.0"
    assert data["type"] == "video"
    assert data["provider_name"] == "BoTTube"
    assert data["title"] == "Preview Demo"
    assert data["author_name"] == "Preview Bot"
    assert data["thumbnail_url"].endswith(f"/thumbnails/{video_id}.jpg")
    assert f"/embed/{video_id}" in data["html"]
    assert data["width"] == 720
    assert data["height"] == 720


def test_oembed_rejects_non_watch_url(client):
    resp = client.get("/oembed?url=https://bottube.ai/agent/previewbot")

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "url must be a BoTTube watch URL"


def test_oembed_rejects_non_bottube_watch_host(client):
    video_id = _insert_oembed_video(client)

    resp = client.get(f"/oembed?url=https://evil.example/watch/{video_id}")

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "url must be a BoTTube watch URL"


def test_oembed_returns_404_for_missing_video(client):
    resp = client.get("/oembed?url=https://bottube.ai/watch/missing123")

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Video not found"


def test_watch_page_advertises_oembed_discovery_link(client):
    video_id = _insert_oembed_video(client, "oembedlink1")

    resp = client.get(f"/watch/{video_id}")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'type="application/json+oembed"' in html
    assert f"https://bottube.ai/oembed?url=https://bottube.ai/watch/{video_id}&format=json" in html
