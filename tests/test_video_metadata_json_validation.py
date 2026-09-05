# SPDX-License-Identifier: MIT
"""Regression coverage for structured JSON in video metadata updates."""

import time

import pytest


def _insert_video(app, agent_name, video_id="metadata01AB"):
    with app.app_context():
        import bottube_server

        db = bottube_server.get_db()
        agent = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
        ).fetchone()
        db.execute(
            """INSERT INTO videos
                   (video_id, agent_id, title, description, tags, filename, created_at)
               VALUES (?, ?, 'Original title', 'Original description', 'one,two', ?, ?)""",
            (video_id, agent["id"], f"{video_id}.mp4", time.time()),
        )
        db.commit()
    return video_id


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"title": {"nested": "title"}}, "title must be a string"),
        ({"description": ["structured"]}, "description must be a string"),
        ({"tags": {"unexpected": "mapping"}}, "tags must be a string or an array of strings"),
        ({"tags": ["valid", {"unexpected": "item"}]}, "tags must be a string or an array of strings"),
    ],
)
def test_video_metadata_rejects_structured_fields_without_mutation(
    app, client, registered_agent, payload, expected_error
):
    video_id = _insert_video(app, registered_agent["agent_name"])

    response = client.patch(
        f"/api/videos/{video_id}",
        headers={"X-API-Key": registered_agent["api_key"]},
        json=payload,
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}
    with app.app_context():
        import bottube_server

        row = bottube_server.get_db().execute(
            "SELECT title, description, tags FROM videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        assert tuple(row) == ("Original title", "Original description", "one,two")


def test_video_metadata_accepts_supported_text_and_tag_array(app, client, registered_agent):
    video_id = _insert_video(app, registered_agent["agent_name"])

    response = client.patch(
        f"/api/videos/{video_id}",
        headers={"X-API-Key": registered_agent["api_key"]},
        json={
            "title": "  Revised title  ",
            "description": "  Revised description  ",
            "tags": [" first ", "second"],
        },
    )

    assert response.status_code == 200
    with app.app_context():
        import bottube_server

        row = bottube_server.get_db().execute(
            "SELECT title, description, tags FROM videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        assert tuple(row) == ("Revised title", "Revised description", "first,second")
