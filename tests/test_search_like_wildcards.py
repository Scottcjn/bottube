# SPDX-License-Identifier: MIT
"""Regression coverage for literal SQLite LIKE metacharacters in search."""

import time
import pytest


def _seed(app, agent_name, literal_id, literal_title):
    with app.app_context():
        import bottube_server
        db = bottube_server.get_db()
        agent = db.execute(
            """INSERT INTO agents (agent_name, display_name, api_key, bio, created_at, last_active)
               VALUES (?, ?, ?, '', ?, ?) RETURNING id""",
            (agent_name, agent_name.title(), f"{agent_name}-key", time.time(), time.time()),
        ).fetchone()
        for video_id, title in [
            (literal_id, literal_title),
            (f"{literal_id}-ordinary", "Ordinary Search Result"),
        ]:
            db.execute(
                """INSERT INTO videos
                   (video_id, agent_id, title, description, filename, tags,
                    category, views, created_at, is_removed)
                   VALUES (?, ?, ?, 'plain description', ?, '[]', 'other', 1, ?, 0)""",
                (video_id, agent["id"], title, f"{video_id}.mp4", time.time()),
            )
        db.commit()


@pytest.mark.parametrize(
    ("needle", "agent_name", "literal_id", "literal_title"),
    [
        ("%", "percentbot", "percent-literal", "Progress 100% Complete"),
        ("_", "underscorebot", "underscore-literal", "Status_Code Literal"),
    ],
)
def test_api_search_treats_like_metacharacters_as_literal_text(
    app, client, needle, agent_name, literal_id, literal_title
):
    _seed(app, agent_name, literal_id, literal_title)
    response = client.get("/api/search", query_string={"q": needle, "per_page": 50})
    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] == 1
    assert [video["video_id"] for video in body["videos"]] == [literal_id]


@pytest.mark.parametrize(
    ("needle", "agent_name", "literal_id", "literal_title"),
    [
        ("%", "percentwebbot", "web-percent", "Web 100% Literal"),
        ("_", "underscorewebbot", "web-underscore", "Web_Status Literal"),
    ],
)
def test_html_search_treats_like_metacharacters_as_literal_text(
    app, client, needle, agent_name, literal_id, literal_title
):
    _seed(app, agent_name, literal_id, literal_title)
    response = client.get("/search", query_string={"q": needle})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert literal_title in html
    assert "Ordinary Search Result" not in html
