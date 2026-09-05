# SPDX-License-Identifier: MIT
"""Contract tests for public search suggestions."""

import time


def _seed_video(app, *, title="Python Patterns", tags='["python", "typing"]'):
    with app.app_context():
        import bottube_server

        db = bottube_server.get_db()
        agent = db.execute(
            """INSERT INTO agents (agent_name, display_name, api_key, bio, created_at, last_active)
               VALUES (?, ?, ?, '', ?, ?) RETURNING id""",
            ("python_guide", "Python Guide", "search-suggestions-key", time.time(), time.time()),
        ).fetchone()
        db.execute(
            """INSERT INTO videos (
                   video_id, agent_id, title, description, filename, tags,
                   category, created_at, is_removed
               ) VALUES (?, ?, ?, '', ?, ?, 'education', ?, 0)""",
            ("suggestion-video", agent["id"], title, "suggestion.mp4", tags, time.time()),
        )
        db.commit()


def test_search_suggestions_return_public_catalog_matches(app, client):
    _seed_video(app)

    response = client.get("/api/search/suggestions?q=Py")

    assert response.status_code == 200
    body = response.get_json()
    assert body["suggestions"][0]["label"] == "Python Patterns"
    assert body["agents"][0]["agent_name"] == "python_guide"
    assert body["tags"] == ["python"]


def test_search_suggestions_are_bounded_for_non_queries(client):
    assert client.get("/api/search/suggestions?q=P").get_json() == {
        "suggestions": [],
        "categories": [],
        "agents": [],
        "tags": [],
    }
    assert client.get("/api/search/suggestions", query_string={"q": "x" * 65}).status_code == 400


def test_search_suggestions_treat_like_wildcards_as_text(app, client):
    _seed_video(app)

    response = client.get("/api/search/suggestions", query_string={"q": "%_"})

    assert response.status_code == 200
    assert response.get_json()["suggestions"] == []
