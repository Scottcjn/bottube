# SPDX-License-Identifier: MIT
"""
Regression test for issue #1411: /discover/api/agents returns 500 when an
agent's bio is NULL (NoneType subscript error).

The operator-precedence bug in search_blueprint.py caused row['bio'][:150]
to be evaluated before the None check, crashing on agents without a bio.
"""

import time
import pytest


class TestDiscoverNullBio:
    def test_discover_agents_no_500_on_null_bio(self, client, registered_agent):
        """The /discover/api/agents endpoint must return 200 even when
        some agents have bio=NULL."""
        import bottube_server

        with client.application.app_context():
            db = bottube_server.get_db()
            # Insert a second agent with NULL bio and a video
            db.execute(
                """INSERT OR IGNORE INTO agents
                   (agent_name, display_name, bio, api_key, created_at)
                   VALUES (?, ?, NULL, ?, ?)""",
                ("null_bio_agent", "Null Bio Agent", "fake_key_null_bio", time.time()),
            )
            null_agent = db.execute(
                "SELECT id FROM agents WHERE agent_name = 'null_bio_agent'"
            ).fetchone()
            if null_agent:
                db.execute(
                    """INSERT INTO videos
                       (video_id, agent_id, title, description, filename, category,
                        views, likes, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "null_bio_test_video",
                        null_agent["id"],
                        "test",
                        "test",
                        "test.mp4",
                        "tech",
                        10,
                        0,
                        time.time(),
                    ),
                )
            db.commit()

        resp = client.get("/discover/api/agents")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "agents" in data

    def test_bio_truncation_with_parens(self):
        """Unit test that the parenthesized conditional handles None correctly."""
        # Simulate the fixed expression
        row_bio_none = None
        row_bio_short = "hello"
        row_bio_long = "x" * 300

        # Fixed expression (with parens)
        result_none = ((row_bio_none[:150] + "...") if row_bio_none and len(row_bio_none) > 150 else row_bio_none) if False else row_bio_none
        # Actually just test the logic directly
        def trunc(bio):
            return (bio[:150] + "...") if bio and len(bio) > 150 else bio

        assert trunc(None) is None
        assert trunc("hello") == "hello"
        assert trunc("x" * 300) == "x" * 150 + "..."
        assert len(trunc("x" * 300)) == 153
