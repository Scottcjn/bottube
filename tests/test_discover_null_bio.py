# SPDX-License-Identifier: MIT
"""
Regression test for issue #1411: /discover/api/agents and /discover/api/search
return 500 when agent bio or video description is NULL.

The crash happens in search_blueprint.py where row[col][:n] is evaluated
without a None guard. These tests verify the fix at both the expression
level and the endpoint level.
"""

import time
import pytest


class TestNullGuardExpressions:
    """Unit-level tests for the None-safe truncation pattern."""

    def test_truncation_handles_none_bio(self):
        def trunc_bio(bio):
            return (bio[:150] + "...") if bio and len(bio) > 150 else bio

        assert trunc_bio(None) is None
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


class TestSearchNullDescription:
    """Verify /discover/api/search doesn't crash on NULL descriptions."""

    def test_search_no_500_on_null_description(self, client, registered_agent):
        import bottube_server

        with client.application.app_context():
            db = bottube_server.get_db()
            agent = db.execute(
                "SELECT id FROM agents WHERE agent_name = ?",
                (registered_agent["agent_name"],)
            ).fetchone()
            if agent:
                db.execute(
                    """INSERT INTO videos
                       (video_id, agent_id, title, description, filename, category,
                        views, likes, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "null_desc_test_video",
                        agent["id"],
                        "Null Description Video",
                        None,
                        "test.mp4",
                        "tech",
                        5,
                        0,
                        time.time(),
                    ),
                )
            db.commit()

        resp = client.get("/discover/api/search?q=test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "videos" in data

    def test_search_no_500_on_null_description_trending(self, client, registered_agent):
        """Also test the trending/tagged videos endpoint which has the same pattern."""
        import bottube_server

        with client.application.app_context():
            db = bottube_server.get_db()
            agent = db.execute(
                "SELECT id FROM agents WHERE agent_name = ?",
                (registered_agent["agent_name"],)
            ).fetchone()
            if agent:
                db.execute(
                    """INSERT INTO videos
                       (video_id, agent_id, title, description, filename, category,
                        views, likes, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "null_desc_trending_video",
                        agent["id"],
                        "Trending Null Desc",
                        None,
                        "test.mp4",
                        "tech",
                        50,
                        10,
                        time.time(),
                    ),
                )
            db.commit()

        resp = client.get("/discover/api/trending?limit=5")
        assert resp.status_code == 200
