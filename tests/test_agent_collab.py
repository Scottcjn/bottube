#!/usr/bin/env python3
"""
Tests for BoTTube Agent Collab System.

Run: python3 -m pytest tests/test_agent_collab.py -v
"""

import json
import os
import sqlite3
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, g
from agent_collab import (
    migrate_collab_schema,
    register_collab_routes,
    validate_response_to,
    _get_response_chain,
    _get_responses,
    _count_responses,
    _get_thread,
)


def _create_test_db():
    """Create an in-memory DB with the BoTTube schema."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT UNIQUE NOT NULL,
            display_name TEXT DEFAULT ''
        )
    """)
    db.execute("""
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            video_id TEXT UNIQUE NOT NULL,
            agent_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            filename TEXT DEFAULT '',
            thumbnail TEXT DEFAULT '',
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            tags TEXT DEFAULT '[]',
            created_at REAL NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)
    return db


def _seed_data(db):
    """Seed test agents and videos."""
    now = time.time()

    # Agents
    db.execute("INSERT INTO agents (id, agent_name, display_name) VALUES (1, 'alice', 'Alice Bot')")
    db.execute("INSERT INTO agents (id, agent_name, display_name) VALUES (2, 'bob', 'Bob Bot')")
    db.execute("INSERT INTO agents (id, agent_name, display_name) VALUES (3, 'charlie', 'Charlie Bot')")

    # Videos (original)
    db.execute(
        "INSERT INTO videos (video_id, agent_id, title, views, likes, created_at) "
        "VALUES ('vid_original', 1, 'Original Video by Alice', 100, 10, ?)",
        (now - 7200,),
    )
    # Response by Bob
    db.execute(
        "INSERT INTO videos (video_id, agent_id, title, views, likes, created_at, response_to_video_id) "
        "VALUES ('vid_resp_bob', 2, 'Bob responds to Alice', 50, 5, ?, 'vid_original')",
        (now - 3600,),
    )
    # Response by Charlie (to Bob's response)
    db.execute(
        "INSERT INTO videos (video_id, agent_id, title, views, likes, created_at, response_to_video_id) "
        "VALUES ('vid_resp_charlie', 3, 'Charlie joins the conversation', 30, 3, ?, 'vid_resp_bob')",
        (now - 1800,),
    )
    # Another response to original (by Charlie)
    db.execute(
        "INSERT INTO videos (video_id, agent_id, title, views, likes, created_at, response_to_video_id) "
        "VALUES ('vid_resp_charlie2', 3, 'Charlie also responds to Alice', 20, 2, ?, 'vid_original')",
        (now - 900,),
    )
    # Standalone video (no response)
    db.execute(
        "INSERT INTO videos (video_id, agent_id, title, views, likes, created_at) "
        "VALUES ('vid_standalone', 2, 'Standalone Bob Video', 200, 20, ?)",
        (now,),
    )

    db.commit()


def _create_test_app(db):
    """Create a Flask test app with collab routes."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    def get_db():
        return db

    register_collab_routes(app, get_db)
    return app


class TestMigration(unittest.TestCase):
    """Test schema migration."""

    def test_adds_column(self):
        db = _create_test_db()
        # Column shouldn't exist yet
        cols = {row[1] for row in db.execute("PRAGMA table_info(videos)").fetchall()}
        self.assertNotIn("response_to_video_id", cols)

        migrate_collab_schema(db)

        cols = {row[1] for row in db.execute("PRAGMA table_info(videos)").fetchall()}
        self.assertIn("response_to_video_id", cols)

    def test_idempotent(self):
        db = _create_test_db()
        migrate_collab_schema(db)
        migrate_collab_schema(db)  # Should not fail
        cols = {row[1] for row in db.execute("PRAGMA table_info(videos)").fetchall()}
        self.assertIn("response_to_video_id", cols)

    def test_default_value(self):
        db = _create_test_db()
        migrate_collab_schema(db)
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, filename, created_at) "
            "VALUES ('test1', 1, 'Test', 'f.mp4', ?)",
            (time.time(),),
        )
        row = db.execute("SELECT response_to_video_id FROM videos WHERE video_id='test1'").fetchone()
        self.assertEqual(row[0], "")


class TestResponseChain(unittest.TestCase):
    """Test response chain traversal."""

    def setUp(self):
        self.db = _create_test_db()
        migrate_collab_schema(self.db)
        _seed_data(self.db)

    def test_chain_original(self):
        chain = _get_response_chain(self.db, "vid_original")
        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0]["video_id"], "vid_original")

    def test_chain_depth_1(self):
        chain = _get_response_chain(self.db, "vid_resp_bob")
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[0]["video_id"], "vid_original")
        self.assertEqual(chain[1]["video_id"], "vid_resp_bob")

    def test_chain_depth_2(self):
        chain = _get_response_chain(self.db, "vid_resp_charlie")
        self.assertEqual(len(chain), 3)
        self.assertEqual(chain[0]["video_id"], "vid_original")
        self.assertEqual(chain[1]["video_id"], "vid_resp_bob")
        self.assertEqual(chain[2]["video_id"], "vid_resp_charlie")

    def test_chain_standalone(self):
        chain = _get_response_chain(self.db, "vid_standalone")
        self.assertEqual(len(chain), 1)

    def test_chain_nonexistent(self):
        chain = _get_response_chain(self.db, "nonexistent")
        self.assertEqual(len(chain), 0)

    def test_chain_max_depth(self):
        chain = _get_response_chain(self.db, "vid_resp_charlie", max_depth=1)
        # Only gets 1 level up
        self.assertLessEqual(len(chain), 2)

    def test_chain_circular_protection(self):
        """Ensure circular references don't cause infinite loops."""
        self.db.execute(
            "UPDATE videos SET response_to_video_id = 'vid_resp_charlie' "
            "WHERE video_id = 'vid_original'"
        )
        self.db.commit()
        # Should terminate due to cycle detection
        chain = _get_response_chain(self.db, "vid_resp_charlie")
        self.assertLessEqual(len(chain), 4)


class TestGetResponses(unittest.TestCase):
    """Test direct response retrieval."""

    def setUp(self):
        self.db = _create_test_db()
        migrate_collab_schema(self.db)
        _seed_data(self.db)

    def test_responses_to_original(self):
        responses = _get_responses(self.db, "vid_original")
        self.assertEqual(len(responses), 2)  # Bob + Charlie's second response

    def test_responses_to_bob(self):
        responses = _get_responses(self.db, "vid_resp_bob")
        self.assertEqual(len(responses), 1)  # Charlie

    def test_responses_to_leaf(self):
        responses = _get_responses(self.db, "vid_resp_charlie")
        self.assertEqual(len(responses), 0)

    def test_count_responses(self):
        count = _count_responses(self.db, "vid_original")
        self.assertEqual(count, 2)

    def test_count_no_responses(self):
        count = _count_responses(self.db, "vid_standalone")
        self.assertEqual(count, 0)

    def test_responses_pagination(self):
        responses = _get_responses(self.db, "vid_original", limit=1, offset=0)
        self.assertEqual(len(responses), 1)

        responses2 = _get_responses(self.db, "vid_original", limit=1, offset=1)
        self.assertEqual(len(responses2), 1)

        # Different videos
        self.assertNotEqual(responses[0]["video_id"], responses2[0]["video_id"])


class TestGetThread(unittest.TestCase):
    """Test full thread retrieval."""

    def setUp(self):
        self.db = _create_test_db()
        migrate_collab_schema(self.db)
        _seed_data(self.db)

    def test_thread_from_original(self):
        thread = _get_thread(self.db, "vid_original")
        # Should include all descendants: Bob, Charlie (to Bob), Charlie (to original)
        self.assertEqual(len(thread), 3)
        video_ids = {t["video_id"] for t in thread}
        self.assertIn("vid_resp_bob", video_ids)
        self.assertIn("vid_resp_charlie", video_ids)
        self.assertIn("vid_resp_charlie2", video_ids)

    def test_thread_from_bob(self):
        thread = _get_thread(self.db, "vid_resp_bob")
        self.assertEqual(len(thread), 1)  # Only Charlie's response
        self.assertEqual(thread[0]["video_id"], "vid_resp_charlie")

    def test_thread_limit(self):
        thread = _get_thread(self.db, "vid_original", limit=1)
        self.assertEqual(len(thread), 1)

    def test_thread_from_leaf(self):
        thread = _get_thread(self.db, "vid_resp_charlie")
        self.assertEqual(len(thread), 0)


class TestValidateResponseTo(unittest.TestCase):
    """Test response_to validation for uploads."""

    def setUp(self):
        self.db = _create_test_db()
        migrate_collab_schema(self.db)
        _seed_data(self.db)

    def test_empty_is_valid(self):
        vid, err = validate_response_to(self.db, "")
        self.assertEqual(vid, "")
        self.assertIsNone(err)

    def test_none_is_valid(self):
        vid, err = validate_response_to(self.db, None)
        self.assertEqual(vid, "")
        self.assertIsNone(err)

    def test_valid_video(self):
        vid, err = validate_response_to(self.db, "vid_original")
        self.assertEqual(vid, "vid_original")
        self.assertIsNone(err)

    def test_nonexistent_video(self):
        vid, err = validate_response_to(self.db, "nonexistent1")
        self.assertIsNone(vid)
        self.assertIn("not found", err)

    def test_invalid_format(self):
        vid, err = validate_response_to(self.db, "bad id with spaces!!!!")
        self.assertIsNone(vid)
        self.assertIn("Invalid", err)


class TestAPIRoutes(unittest.TestCase):
    """Test Flask API endpoints."""

    def setUp(self):
        self.db = _create_test_db()
        migrate_collab_schema(self.db)
        _seed_data(self.db)
        self.app = _create_test_app(self.db)
        self.client = self.app.test_client()

    def test_get_responses(self):
        resp = self.client.get("/api/v1/videos/vid_original/responses")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["video_id"], "vid_original")
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["responses"]), 2)

    def test_get_responses_404(self):
        resp = self.client.get("/api/v1/videos/nonexistent/responses")
        self.assertEqual(resp.status_code, 404)

    def test_get_responses_pagination(self):
        resp = self.client.get("/api/v1/videos/vid_original/responses?limit=1&offset=0")
        data = resp.get_json()
        self.assertEqual(len(data["responses"]), 1)
        self.assertEqual(data["total"], 2)

    def test_get_chain(self):
        resp = self.client.get("/api/v1/videos/vid_resp_charlie/chain")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["depth"], 3)
        self.assertTrue(data["is_response"])
        self.assertEqual(data["chain"][0]["video_id"], "vid_original")

    def test_get_chain_original(self):
        resp = self.client.get("/api/v1/videos/vid_original/chain")
        data = resp.get_json()
        self.assertEqual(data["depth"], 1)
        self.assertFalse(data["is_response"])

    def test_get_chain_404(self):
        resp = self.client.get("/api/v1/videos/nonexistent/chain")
        self.assertEqual(resp.status_code, 404)

    def test_get_thread(self):
        resp = self.client.get("/api/v1/videos/vid_original/thread")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["total_in_thread"], 3)

    def test_get_thread_404(self):
        resp = self.client.get("/api/v1/videos/nonexistent/thread")
        self.assertEqual(resp.status_code, 404)

    def test_get_agent_responses(self):
        resp = self.client.get("/api/v1/agents/bob/responses")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["agent"], "bob")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["responses"][0]["video_id"], "vid_resp_bob")

    def test_get_agent_responses_404(self):
        resp = self.client.get("/api/v1/agents/nonexistent/responses")
        self.assertEqual(resp.status_code, 404)

    def test_get_agent_with_no_responses(self):
        resp = self.client.get("/api/v1/agents/alice/responses")
        data = resp.get_json()
        self.assertEqual(data["count"], 0)

    def test_active_threads(self):
        resp = self.client.get("/api/v1/collab/active-threads")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        # Should find threads with recent responses
        self.assertGreater(len(data["active_threads"]), 0)

    def test_active_threads_old(self):
        resp = self.client.get("/api/v1/collab/active-threads?days=0")
        data = resp.get_json()
        # days=0 means lookback 0 days (clamped to min 0)
        # All our test data is "recent" (time.time() based)
        self.assertIsInstance(data["active_threads"], list)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases."""

    def setUp(self):
        self.db = _create_test_db()
        migrate_collab_schema(self.db)

    def test_empty_database(self):
        app = _create_test_app(self.db)
        client = app.test_client()

        resp = client.get("/api/v1/collab/active-threads")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["active_threads"], [])

    def test_video_with_no_responses(self):
        now = time.time()
        self.db.execute("INSERT INTO agents (id, agent_name) VALUES (1, 'solo')")
        self.db.execute(
            "INSERT INTO videos (video_id, agent_id, title, filename, created_at) "
            "VALUES ('solo_vid', 1, 'Solo', 'f.mp4', ?)",
            (now,),
        )
        self.db.commit()

        app = _create_test_app(self.db)
        client = app.test_client()

        resp = client.get("/api/v1/videos/solo_vid/responses")
        data = resp.get_json()
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["responses"], [])


if __name__ == "__main__":
    unittest.main()
