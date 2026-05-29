# SPDX-License-Identifier: MIT
import time


def _insert_agent(db, name="cache_owner"):
    cur = db.execute(
        """
        INSERT INTO agents (agent_name, display_name, api_key, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (name, name.replace("_", " ").title(), f"{name}_key", time.time()),
    )
    return int(cur.lastrowid)


def _insert_video(db, agent_id, video_id, created_at):
    db.execute(
        """
        INSERT INTO videos (video_id, agent_id, title, filename, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (video_id, agent_id, f"Video {video_id}", f"{video_id}.mp4", created_at),
    )


def test_video_list_returns_cache_validators(app, client):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        agent_id = _insert_agent(db)
        _insert_video(db, agent_id, "cache_video_1", 1_800_000_000)
        db.commit()

    response = client.get("/api/videos")

    assert response.status_code == 200
    assert response.headers["ETag"].startswith('W/"videos-')
    assert response.headers["Last-Modified"] == "Fri, 15 Jan 2027 08:00:00 GMT"
    assert response.headers["Cache-Control"] == "public, max-age=30"


def test_video_list_if_none_match_returns_304(app, client):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        agent_id = _insert_agent(db)
        _insert_video(db, agent_id, "cache_video_2", 1_800_000_000)
        db.commit()

    first = client.get("/api/videos")
    response = client.get("/api/videos", headers={"If-None-Match": first.headers["ETag"]})

    assert response.status_code == 304
    assert response.data == b""
    assert response.headers["ETag"] == first.headers["ETag"]
    assert response.headers["Cache-Control"] == "public, max-age=30"


def test_video_list_if_modified_since_returns_304(app, client):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        agent_id = _insert_agent(db)
        _insert_video(db, agent_id, "cache_video_3", 1_800_000_000)
        db.commit()

    first = client.get("/api/videos")
    response = client.get(
        "/api/videos",
        headers={"If-Modified-Since": first.headers["Last-Modified"]},
    )

    assert response.status_code == 304
    assert response.headers["ETag"] == first.headers["ETag"]


def test_video_list_etag_changes_after_newer_video(app, client):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        agent_id = _insert_agent(db)
        _insert_video(db, agent_id, "cache_video_4", 1_800_000_000)
        db.commit()

    first = client.get("/api/videos")

    with app.app_context():
        db = bottube_server.get_db()
        _insert_video(db, agent_id, "cache_video_5", 1_800_000_060)
        db.commit()

    second = client.get("/api/videos")

    assert second.status_code == 200
    assert second.headers["ETag"] != first.headers["ETag"]
    assert second.headers["Last-Modified"] == "Fri, 15 Jan 2027 08:01:00 GMT"


def test_video_list_etag_changes_after_visible_engagement(app, client):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        agent_id = _insert_agent(db)
        _insert_video(db, agent_id, "cache_video_6", 1_800_000_000)
        db.commit()

    first = client.get("/api/videos")

    with app.app_context():
        db = bottube_server.get_db()
        db.execute("UPDATE videos SET views = views + 1 WHERE video_id = ?", ("cache_video_6",))
        db.execute(
            "INSERT INTO views (video_id, ip_address, created_at) VALUES (?, ?, ?)",
            ("cache_video_6", "203.0.113.6", 1_800_000_060),
        )
        db.commit()

    second = client.get("/api/videos")

    assert second.status_code == 200
    assert second.headers["ETag"] != first.headers["ETag"]
    assert second.headers["Last-Modified"] == "Fri, 15 Jan 2027 08:01:00 GMT"


def test_video_list_if_modified_since_sees_engagement_on_older_video(app, client):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        agent_id = _insert_agent(db)
        _insert_video(db, agent_id, "cache_newer_video", 1_800_000_200)
        _insert_video(db, agent_id, "cache_older_video", 1_800_000_000)
        db.commit()

    first = client.get("/api/videos")

    with app.app_context():
        db = bottube_server.get_db()
        db.execute("UPDATE videos SET likes = likes + 1 WHERE video_id = ?", ("cache_older_video",))
        db.execute(
            "INSERT INTO votes (agent_id, video_id, vote, created_at) VALUES (?, ?, ?, ?)",
            (agent_id, "cache_older_video", 1, 1_800_000_260),
        )
        db.commit()

    second = client.get(
        "/api/videos",
        headers={"If-Modified-Since": first.headers["Last-Modified"]},
    )

    assert second.status_code == 200
    assert second.headers["ETag"] != first.headers["ETag"]
    assert second.headers["Last-Modified"] == "Fri, 15 Jan 2027 08:04:20 GMT"
