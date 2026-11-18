# SPDX-License-Identifier: MIT
import time
import pytest


def _create_video_with_comments(client, count=5):
    """Helper to insert an agent, a video, and multiple comments into the test DB."""
    with client.application.app_context():
        from bottube_server import get_db
        db = get_db()
        cur = db.execute(
            """INSERT INTO agents (agent_name, display_name, api_key, created_at)
               VALUES ('test_agent', 'Test Agent', 'test_key', ?)""",
            (time.time(),),
        )
        agent_id = cur.lastrowid
        db.execute(
            """INSERT INTO videos (video_id, agent_id, title, filename, created_at)
               VALUES ('test_vid_pagination', ?, 'Test Vid', 'test.mp4', ?)""",
            (agent_id, time.time()),
        )
        for i in range(count):
            db.execute(
                """INSERT INTO comments (video_id, agent_id, content, created_at)
                   VALUES ('test_vid_pagination', ?, ?, ?)""",
                (agent_id, f"Comment {i+1}", time.time() + i),
            )
        db.commit()


def test_get_comments_unpaginated_backwards_compatible(client):
    _create_video_with_comments(client, count=5)
    response = client.get("/api/videos/test_vid_pagination/comments")
    assert response.status_code == 200
    data = response.get_json()
    assert "comments" in data
    assert "count" in data
    assert data["count"] == 5
    assert len(data["comments"]) == 5
    assert "page" not in data


def test_get_comments_paginated_slices(client):
    _create_video_with_comments(client, count=5)
    # Page 1, per_page 2
    r1 = client.get("/api/videos/test_vid_pagination/comments?page=1&per_page=2")
    assert r1.status_code == 200
    d1 = r1.get_json()
    assert d1["page"] == 1
    assert d1["per_page"] == 2
    assert d1["total"] == 5
    assert d1["total_pages"] == 3
    assert d1["count"] == 2
    assert len(d1["comments"]) == 2
    assert d1["has_next"] is True

    # Page 3, per_page 2
    r3 = client.get("/api/videos/test_vid_pagination/comments?page=3&per_page=2")
    assert r3.status_code == 200
    d3 = r3.get_json()
    assert d3["page"] == 3
    assert d3["count"] == 1
    assert len(d3["comments"]) == 1
    assert d3["has_next"] is False


@pytest.mark.parametrize(
    ("param", "value", "expected_error"),
    [
        ("page", "abc", "page must be an integer"),
        ("page", "0", "page must be >= 1"),
        ("page", "-5", "page must be >= 1"),
        ("page", "10001", "page must be <= 10000"),
        ("per_page", "xyz", "per_page must be an integer"),
        ("per_page", "0", "per_page must be >= 1"),
        ("per_page", "-1", "per_page must be >= 1"),
        ("per_page", "101", "per_page must be <= 100"),
    ],
)
def test_get_comments_pagination_validation_errors(client, param, value, expected_error):
    _create_video_with_comments(client, count=1)
    response = client.get(f"/api/videos/test_vid_pagination/comments?{param}={value}")
    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == expected_error
