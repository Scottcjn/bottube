# SPDX-License-Identifier: MIT
"""
Regression test: /discover/api/agents and /discover/api/search
crash with HTTP 500 when agent bio or video description is NULL.

The root cause is unguarded row[col][:n] slices in search_blueprint.py.
"""

import time
import pytest


class TestNullGuardExpressions:
    """Unit-level tests for the None-safe truncation pattern."""

    def test_truncation_handles_none_bio(self):
        def trunc_bio(bio):
            return (bio[:150] + "...") if bio and len(bio) > 150 else (bio or "")
        assert trunc_bio(None) == ""
        assert trunc_bio("") == ""
        assert trunc_bio("short") == "short"
        assert trunc_bio("x" * 300) == "x" * 150 + "..."

    def test_truncation_handles_none_description(self):
        def trunc_desc(desc, max_len):
            return (desc[:max_len] + "...") if desc and len(desc) > max_len else (desc or "")
        assert trunc_desc(None, 200) == ""
        assert trunc_desc(None, 150) == ""
        assert trunc_desc("short", 200) == "short"
        assert trunc_desc("x" * 300, 200) == "x" * 200 + "..."


class TestNullBioNoCrash:
    """Insert NULL bio/description rows and verify endpoints return 200."""

    def _patch_search_get_db(self, app):
        """Patch search_blueprint.get_db to use the app's DB."""
        import bottube_server
        import search_blueprint
        search_blueprint.get_db = bottube_server.get_db

    def _seed_null_desc_video(self, app, agent_name, video_id):
        """Insert a video with NULL description via the app's DB."""
        import bottube_server
        with app.app_context():
            db = bottube_server.get_db()
            agent = db.execute(
                "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
            ).fetchone()
            if agent:
                db.execute(
                    """INSERT OR REPLACE INTO videos
                       (video_id, agent_id, title, description, filename, category,
                        views, likes, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (video_id, agent["id"], "Null Desc Test",
                     None, "test.mp4", "tech", 5, 0, time.time()),
                )
            db.commit()

    def test_search_no_500_on_null_description(self, app, client, registered_agent):
        self._patch_search_get_db(app)
        self._seed_null_desc_video(app, registered_agent["agent_name"], "null_desc_search")

        resp = client.get("/discover/api/search?q=null")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "videos" in data

    def test_agents_no_500_on_null_bio(self, app, client, registered_agent):
        import bottube_server
        self._patch_search_get_db(app)

        with app.app_context():
            db = bottube_server.get_db()
            agent = db.execute(
                "SELECT id FROM agents WHERE agent_name = ?",
                (registered_agent["agent_name"],)
            ).fetchone()
            if agent:
                db.execute(
                    """INSERT OR REPLACE INTO videos
                       (video_id, agent_id, title, description, filename, category,
                        views, likes, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("null_bio_video", agent["id"], "Has Desc",
                     "some desc", "test.mp4", "tech", 5, 0, time.time()),
                )
            db.execute(
                "UPDATE agents SET bio = NULL WHERE agent_name = ?",
                (registered_agent["agent_name"],)
            )
            db.commit()

        resp = client.get("/discover/api/agents?limit=10")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "agents" in data

    def test_for_you_no_500_on_null_description(self, app, client, registered_agent):
        self._patch_search_get_db(app)
        self._seed_null_desc_video(app, registered_agent["agent_name"], "null_desc_foryou")

        resp = client.get("/discover/api/for-you")
        assert resp.status_code == 200
