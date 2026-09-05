# SPDX-License-Identifier: MIT
import time


def _insert_agent(db, name, *, banned=False):
    cursor = db.execute(
        """
        INSERT INTO agents
            (agent_name, display_name, api_key, password_hash, bio,
             avatar_url, is_human, is_banned, created_at, last_active)
        VALUES (?, ?, ?, '', '', '', 0, ?, ?, ?)
        """,
        (
            name,
            name.replace("_", " ").title(),
            f"bottube_sk_{name}",
            int(banned),
            time.time(),
            time.time(),
        ),
    )
    return int(cursor.lastrowid)


def _insert_video(db, video_id, agent_id, *, removed=False):
    db.execute(
        """
        INSERT INTO videos
            (video_id, agent_id, title, filename, thumbnail, created_at,
             is_removed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            video_id,
            agent_id,
            f"Video {video_id}",
            f"{video_id}.mp4",
            f"{video_id}.jpg",
            time.time(),
            int(removed),
        ),
    )


def test_similar_rejects_banned_source_before_embedding_lookup(client, monkeypatch):
    import bottube_server

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        owner_id = _insert_agent(db, "similar_banned_source", banned=True)
        _insert_video(db, "similar_banned_source_video", owner_id)
        db.commit()

    def fail_lookup(*args, **kwargs):
        raise AssertionError("embedding lookup should not run for a hidden video")

    monkeypatch.setattr(bottube_server, "_ue_top_k_for_video", fail_lookup)

    response = client.get("/api/videos/similar_banned_source_video/similar")

    assert response.status_code == 404
    assert response.get_json() == {
        "ok": False,
        "error": "video not found",
        "video_id": "similar_banned_source_video",
    }


def test_similar_results_exclude_removed_and_banned_creator_videos(
    client, monkeypatch
):
    import bottube_server

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        visible_owner = _insert_agent(db, "similar_visible_owner")
        banned_owner = _insert_agent(db, "similar_banned_owner", banned=True)
        _insert_video(db, "similar_public_source", visible_owner)
        _insert_video(db, "similar_visible_result", visible_owner)
        _insert_video(db, "similar_removed_result", visible_owner, removed=True)
        _insert_video(db, "similar_banned_result", banned_owner)
        db.commit()

    monkeypatch.setattr(
        bottube_server,
        "_ue_top_k_for_video",
        lambda *args, **kwargs: [
            ("similar_visible_result", 0.91),
            ("similar_removed_result", 0.89),
            ("similar_banned_result", 0.87),
        ],
    )

    response = client.get("/api/videos/similar_public_source/similar?k=3")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert [row["video_id"] for row in payload["results"]] == [
        "similar_visible_result"
    ]
