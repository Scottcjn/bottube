# SPDX-License-Identifier: MIT
"""Regression coverage for structured JSON in cross-post requests."""

import time

import pytest


def _insert_video(app, agent_name, video_id="crosspost01A"):
    with app.app_context():
        import bottube_server

        db = bottube_server.get_db()
        agent = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
        ).fetchone()
        db.execute(
            """INSERT INTO videos
                   (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, 'Cross-post source', ?, ?)""",
            (video_id, agent["id"], f"{video_id}.mp4", time.time()),
        )
        db.commit()
    return video_id


@pytest.mark.parametrize(
    ("path", "payload", "expected_error"),
    [
        ("/api/crosspost/moltbook", ["not", "an", "object"], "JSON body must be an object"),
        ("/api/crosspost/moltbook", {"video_id": {"nested": "id"}}, "video_id must be a string"),
        (
            "/api/crosspost/moltbook",
            {"video_id": "crosspost01A", "submolt": {"nested": "name"}},
            "submolt must be a string",
        ),
        ("/api/crosspost/x", {"video_id": {"nested": "id"}}, "video_id must be a string"),
        (
            "/api/crosspost/x",
            {"video_id": "crosspost01A", "text": {"nested": "tweet"}},
            "text must be a string",
        ),
    ],
)
def test_crosspost_routes_reject_structured_fields_before_side_effects(
    app, client, registered_agent, monkeypatch, path, payload, expected_error
):
    import bottube_server

    _insert_video(app, registered_agent["agent_name"])

    def unexpected_post(_text):
        raise AssertionError("X client must not run for malformed JSON")

    monkeypatch.setattr(bottube_server, "_post_to_x", unexpected_post)
    response = client.post(
        path,
        headers={"X-API-Key": registered_agent["api_key"]},
        json=payload,
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}
    with app.app_context():
        assert bottube_server.get_db().execute(
            "SELECT COUNT(*) FROM crossposts"
        ).fetchone()[0] == 0


def test_supported_crosspost_payloads_preserve_existing_flows(
    app, client, registered_agent, monkeypatch
):
    import bottube_server

    video_id = _insert_video(app, registered_agent["agent_name"])
    headers = {"X-API-Key": registered_agent["api_key"]}
    monkeypatch.setattr(bottube_server, "_post_to_x", lambda text: "tweet-123")

    moltbook = client.post(
        "/api/crosspost/moltbook",
        headers=headers,
        json={"video_id": video_id, "submolt": "bottube"},
    )
    x_post = client.post(
        "/api/crosspost/x",
        headers=headers,
        json={"video_id": video_id, "text": "A valid announcement"},
    )

    assert moltbook.status_code == 200
    assert x_post.status_code == 200
    assert x_post.get_json()["tweet_id"] == "tweet-123"
    with app.app_context():
        rows = bottube_server.get_db().execute(
            "SELECT platform, external_id FROM crossposts ORDER BY id"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("moltbook", None),
            ("x", "tweet-123"),
        ]
