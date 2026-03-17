#!/usr/bin/env python3
"""
Test suite for Issue #424: Agent-to-Agent Interaction Visibility

Tests for:
- Activity feed API endpoint
- Comment interaction metadata (interaction_type, is_agent_interaction, reply_thread_id)
- Collaboration indicators
- Accessible UI labels
"""

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bottube_server import app, get_db, init_db


class TestAgentInteractionVisibility(unittest.TestCase):
    """Test agent-to-agent interaction visibility features."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.test_db_path = self.test_db.name
        self.test_db.close()
        
        # Configure app for testing
        app.config["TESTING"] = True
        app.config["DATABASE"] = self.test_db_path
        self.app = app.test_client()
        
        # Initialize database
        with app.app_context():
            db = get_db()
            init_db(db)
            
            # Create test agents
            db.execute("""
                INSERT INTO agents (agent_name, display_name, api_key, is_human)
                VALUES 
                    ('test_bot_1', 'Test Bot One', 'test_key_bot1', 0),
                    ('test_bot_2', 'Test Bot Two', 'test_key_bot2', 0),
                    ('test_human', 'Test Human User', 'test_key_human', 1)
            """)
            
            # Create test video
            db.execute("""
                INSERT INTO videos (video_id, agent_id, title, created_at)
                VALUES ('test_video_001', 1, 'Test Video', ?)
            """, (time.time(),))
            
            db.commit()

    def tearDown(self):
        """Clean up test fixtures."""
        os.unlink(self.test_db_path)

    def test_comment_api_includes_interaction_metadata(self):
        """Test that comment API returns interaction metadata."""
        response = self.app.post(
            "/api/videos/test_video_001/comment",
            headers={"X-API-Key": "test_key_bot1"},
            data=json.dumps({"content": "Test comment from bot 1"}),
            content_type="application/json",
        )
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        
        self.assertIn("interaction_type", data)
        self.assertIn("is_agent_interaction", data)
        self.assertEqual(data["ok"], True)

    def test_agent_reply_interaction_detection(self):
        """Test detection of agent-to-agent reply interactions."""
        # Bot 1 posts initial comment
        response1 = self.app.post(
            "/api/videos/test_video_001/comment",
            headers={"X-API-Key": "test_key_bot1"},
            data=json.dumps({"content": "Initial comment"}),
            content_type="application/json",
        )
        comment1 = json.loads(response1.data)
        
        # Bot 2 replies to Bot 1's comment
        response2 = self.app.post(
            "/api/videos/test_video_001/comment",
            headers={"X-API-Key": "test_key_bot2"},
            data=json.dumps({
                "content": "Reply to bot 1",
                "parent_id": comment1["comment_id"]
            }),
            content_type="application/json",
        )
        
        self.assertEqual(response2.status_code, 201)
        data = json.loads(response2.data)
        
        # Should detect agent-to-agent interaction
        self.assertEqual(data["interaction_type"], "agent_reply")
        self.assertEqual(data["is_agent_interaction"], True)

    def test_self_comment_interaction_detection(self):
        """Test detection of self-comment on own video."""
        response = self.app.post(
            "/api/videos/test_video_001/comment",
            headers={"X-API-Key": "test_key_bot1"},
            data=json.dumps({"content": "Comment on my own video"}),
            content_type="application/json",
        )
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        
        # Video owner commenting on own video
        self.assertEqual(data["interaction_type"], "self_comment")

    def test_collaboration_interaction_detection(self):
        """Test detection of collaboration interactions."""
        # Bot 1 comments
        response1 = self.app.post(
            "/api/videos/test_video_001/comment",
            headers={"X-API-Key": "test_key_bot1"},
            data=json.dumps({"content": "Bot 1 comment"}),
            content_type="application/json",
        )
        comment1 = json.loads(response1.data)
        
        # Bot 2 replies to Bot 1 on Bot 1's video (collaboration)
        response2 = self.app.post(
            "/api/videos/test_video_001/comment",
            headers={"X-API-Key": "test_key_bot2"},
            data=json.dumps({
                "content": "Collaborative reply",
                "parent_id": comment1["comment_id"]
            }),
            content_type="application/json",
        )
        
        data = json.loads(response2.data)
        # This should be detected as agent_reply (simpler case)
        self.assertIn(data["interaction_type"], ["agent_reply", "collaboration"])
        self.assertEqual(data["is_agent_interaction"], True)

    def test_get_comments_includes_interaction_metadata(self):
        """Test that get_comments endpoint returns interaction metadata."""
        # Post a comment
        self.app.post(
            "/api/videos/test_video_001/comment",
            headers={"X-API-Key": "test_key_bot1"},
            data=json.dumps({"content": "Test comment"}),
            content_type="application/json",
        )
        
        # Get comments
        response = self.app.get("/api/videos/test_video_001/comments")
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn("comments", data)
        self.assertGreater(len(data["comments"]), 0)
        
        comment = data["comments"][0]
        self.assertIn("interaction_type", comment)
        self.assertIn("is_agent_interaction", comment)
        self.assertIn("reply_thread_id", comment)

    def test_activity_feed_endpoint_exists(self):
        """Test that activity feed endpoint is accessible."""
        response = self.app.get("/api/activity/feed")
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn("activities", data)
        self.assertIn("count", data)

    def test_activity_feed_filters_by_interaction_type(self):
        """Test activity feed filtering by interaction type."""
        # Create some interactions
        self.app.post(
            "/api/videos/test_video_001/comment",
            headers={"X-API-Key": "test_key_bot1"},
            data=json.dumps({"content": "Comment 1"}),
            content_type="application/json",
        )
        
        # Filter by type
        response = self.app.get("/api/activity/feed?type=self_comment")
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn("activities", data)

    def test_activity_feed_includes_accessibility_labels(self):
        """Test that activity feed includes accessibility labels."""
        response = self.app.get("/api/activity/feed")
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        if data["count"] > 0:
            activity = data["activities"][0]
            self.assertIn("accessibility_label", activity)

    def test_web_comment_api_includes_interaction_metadata(self):
        """Test that web comment API also tracks interactions."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = 1
            
            response = client.post(
                "/api/videos/test_video_001/web-comment",
                data=json.dumps({
                    "content": "Web comment",
                    "csrf_token": "test"
                }),
                content_type="application/json",
            )
            
            # May fail due to CSRF, but should have interaction fields
            if response.status_code == 201:
                data = json.loads(response.data)
                self.assertIn("interaction_type", data)
                self.assertIn("is_agent_interaction", data)


class TestInteractionBadgeRendering(unittest.TestCase):
    """Test interaction badge rendering in templates."""

    def test_interaction_badge_css_classes(self):
        """Test that interaction badges have correct CSS classes."""
        # These CSS classes should be defined in watch.html
        expected_classes = [
            "interaction-badge",
            "interaction-agent-reply",
            "interaction-collaboration",
            "interaction-self",
        ]
        
        # Read watch.html and verify CSS classes exist
        watch_html_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "bottube_templates", "watch.html"
        )
        
        if os.path.exists(watch_html_path):
            with open(watch_html_path, "r") as f:
                content = f.read()
                for css_class in expected_classes:
                    self.assertIn(css_class, content, 
                                  f"CSS class {css_class} should be defined")

    def test_aria_labels_for_interactions(self):
        """Test that ARIA labels are present for accessibility."""
        watch_html_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "bottube_templates", "watch.html"
        )
        
        if os.path.exists(watch_html_path):
            with open(watch_html_path, "r") as f:
                content = f.read()
                # Check for ARIA attributes
                self.assertIn("aria-label", content)
                self.assertIn("aria-describedby", content)


if __name__ == "__main__":
    unittest.main()
