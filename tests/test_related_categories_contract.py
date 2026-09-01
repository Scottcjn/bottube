# SPDX-License-Identifier: MIT
"""Contract tests for the documented related-categories discovery surface."""

import sys
import time


def _seed_animation_counts(app, agent_name):
    server = sys.modules["bottube_server"]
    with app.app_context():
        db = server.get_db()
        agent_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
        ).fetchone()["id"]
        db.executemany(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, category, is_removed, created_at)
               VALUES (?, ?, ?, ?, 'animation', ?, ?)""",
            (
                ("related-cat-visible", agent_id, "Visible animation", "visible.mp4", 0, time.time()),
                ("related-cat-removed", agent_id, "Removed animation", "removed.mp4", 1, time.time()),
            ),
        )
        db.commit()


def test_related_categories_endpoint_matches_documented_shape(
    app, client, registered_agent
):
    _seed_animation_counts(app, registered_agent["agent_name"])

    response = client.get("/api/categories/ai-art/related")

    assert response.status_code == 200
    body = response.get_json()
    assert body["category"] == "ai-art"
    assert [item["id"] for item in body["related"]] == ["animation", "3d", "film"]
    assert body["related"][0]["video_count"] == 1
    assert {"id", "name", "icon", "desc", "video_count"} <= set(body["related"][0])


def test_related_categories_reject_unknown_category(client):
    response = client.get("/api/categories/not-a-category/related")

    assert response.status_code == 404


def test_category_page_receives_related_category_context(client, monkeypatch):
    server = sys.modules["bottube_server"]
    rendered = {}

    def capture_template(_template, **context):
        rendered.update(context)
        return "rendered"

    monkeypatch.setattr(server, "render_template", capture_template)
    response = client.get("/category/ai-art")

    assert response.status_code == 200
    assert [item["id"] for item in rendered["related_categories"]] == [
        "animation",
        "3d",
        "film",
    ]
