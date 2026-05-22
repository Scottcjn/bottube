import time


def _insert_video(video_id="similar01"):
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
                "similar_bot",
                "Similar Bot",
                "bottube_sk_similar",
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
                "Similar route validation",
                f"{video_id}.mp4",
                time.time(),
            ),
        )
        db.commit()
    return video_id


def test_similar_rejects_missing_video_before_embedding_lookup(
    client, monkeypatch
):
    import bottube_server

    def fail_lookup(*args, **kwargs):
        raise AssertionError("embedding lookup should not run")

    monkeypatch.setattr(bottube_server, "_ue_top_k_for_video", fail_lookup)

    response = client.get("/api/videos/missing-similar/similar")

    assert response.status_code == 404
    assert response.get_json() == {
        "ok": False,
        "error": "video not found",
        "video_id": "missing-similar",
    }


def test_similar_preserves_no_embeddings_for_existing_video(
    client, monkeypatch
):
    import bottube_server

    video_id = _insert_video()
    monkeypatch.setattr(
        bottube_server, "_ue_top_k_for_video", lambda *args, **kwargs: []
    )

    response = client.get(f"/api/videos/{video_id}/similar")

    assert response.status_code == 404
    assert response.get_json() == {
        "ok": False,
        "error": "no_embeddings_yet",
        "video_id": video_id,
    }
