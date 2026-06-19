# SPDX-License-Identifier: MIT
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


def test_similar_rejects_invalid_k_values_before_embedding_lookup(
    client, monkeypatch
):
    import bottube_server

    video_id = _insert_video("similar_invalid_k")
    calls = []

    def record_lookup(*args, **kwargs):
        calls.append((args, kwargs))
        return []

    monkeypatch.setattr(bottube_server, "_ue_top_k_for_video", record_lookup)

    cases = {
        "k=abc": "k must be an integer",
        "k=0": "k must be >= 1",
        "k=51": "k must be <= 50",
    }

    for query, expected_error in cases.items():
        response = client.get(f"/api/videos/{video_id}/similar?{query}")

        assert response.status_code == 400
        assert response.get_json() == {"error": expected_error}

    assert calls == []


def test_similar_accepts_default_and_boundary_k_values(client, monkeypatch):
    import bottube_server

    video_id = _insert_video("similar_valid_k")
    calls = []

    def record_lookup(*args, **kwargs):
        calls.append(kwargs["k"])
        return []

    monkeypatch.setattr(bottube_server, "_ue_top_k_for_video", record_lookup)

    default_response = client.get(f"/api/videos/{video_id}/similar")
    lower_response = client.get(f"/api/videos/{video_id}/similar?k=1")
    upper_response = client.get(f"/api/videos/{video_id}/similar?k=50")

    assert default_response.status_code == 404
    assert lower_response.status_code == 404
    assert upper_response.status_code == 404
    assert default_response.get_json()["error"] == "no_embeddings_yet"
    assert lower_response.get_json()["error"] == "no_embeddings_yet"
    assert upper_response.get_json()["error"] == "no_embeddings_yet"
    assert calls == [10, 1, 50]
