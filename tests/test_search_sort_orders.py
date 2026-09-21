# SPDX-License-Identifier: MIT
"""Regression: GET /api/search must honor sort=relevance|newest|views.

Before the fix the route's whitelist only knew views|likes|recent|trending,
so the documented ``relevance`` and ``newest`` keys silently fell back to the
``views`` default and all three sorts returned the identical order (confirmed
live on bottube.ai 2026-09-21). Unknown sort keys are now a 400 rather than a
silent degrade.
"""

import time

import pytest


def _insert(db, video_id, agent_id, title, *, tags, views, age_s):
    db.execute(
        """INSERT INTO videos
           (video_id, agent_id, title, description, tags, filename, category,
            views, likes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'other', ?, 0, ?)""",
        (video_id, agent_id, title, "needle in the body text", tags,
         f"{video_id}.mp4", views, time.time() - age_s),
    )


@pytest.fixture
def seeded(client, registered_agent):
    import bottube_server

    with client.application.app_context():
        db = bottube_server.get_db()
        agent_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            (registered_agent["agent_name"],),
        ).fetchone()["id"]
        # Three videos that all match "needle" (in the description) but differ
        # on every sort axis, so each sort has a distinct winner:
        #   title_hit  - only one with "needle" in the title, fewest views, middle age
        #   most_views - most views, oldest
        #   newest     - newest, middle views
        _insert(db, "title_hit", agent_id, "Needle tutorial", tags="[]",
                views=1, age_s=3600)
        _insert(db, "most_views", agent_id, "Popular clip", tags="[]",
                views=500, age_s=7200)
        _insert(db, "newest", agent_id, "Fresh clip", tags="[]",
                views=50, age_s=0)
        db.commit()
    return client


def _ids(client, sort):
    resp = client.get(f"/api/search?q=needle&sort={sort}")
    assert resp.status_code == 200, resp.get_json()
    return [v["video_id"] for v in resp.get_json()["videos"]]


def test_views_newest_and_relevance_give_different_orders(seeded):
    by_views = _ids(seeded, "views")
    by_newest = _ids(seeded, "newest")
    by_relevance = _ids(seeded, "relevance")

    assert by_views == ["most_views", "newest", "title_hit"]
    assert by_newest == ["newest", "title_hit", "most_views"]
    assert by_relevance[0] == "title_hit"
    assert by_relevance[1:] == ["most_views", "newest"]
    assert len({tuple(by_views), tuple(by_newest), tuple(by_relevance)}) == 3


def test_newest_matches_recent_alias(seeded):
    assert _ids(seeded, "newest") == _ids(seeded, "recent")


def test_unknown_sort_is_rejected(seeded):
    resp = seeded.get("/api/search?q=needle&sort=bogus")
    assert resp.status_code == 400
    body = resp.get_json()
    assert "relevance" in body["allowed"]
    assert "newest" in body["allowed"]
