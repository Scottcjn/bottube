#!/usr/bin/env python3
"""
Tests for the BoTTube Debate Bot Framework.

Run: python3 -m pytest tests/test_debate_framework.py -v
"""

import time
import unittest
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bots.debate_framework import DebateBot, DebateScoreTracker, DebateState


# ---------------------------------------------------------------------------
# Concrete test bot (since DebateBot is abstract)
# ---------------------------------------------------------------------------

class TestBot(DebateBot):
    name = "test-bot"
    personality = "A test bot that always agrees."

    def generate_reply(self, opponent_text, context):
        return f"Reply to: {opponent_text[:50]} (round {context['round_number']})"


class OpponentBot(DebateBot):
    name = "opponent-bot"
    personality = "A test opponent."

    def generate_reply(self, opponent_text, context):
        return f"Opponent reply round {context['round_number']}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDebateBotInit(unittest.TestCase):
    """Test bot initialization."""

    def test_default_init(self):
        bot = TestBot(api_key="test-key")
        self.assertEqual(bot.name, "test-bot")
        self.assertEqual(bot.api_key, "test-key")
        self.assertEqual(bot.base_url, "https://bottube.ai")

    def test_custom_base_url(self):
        bot = TestBot(base_url="http://localhost:5000", api_key="k")
        self.assertEqual(bot.base_url, "http://localhost:5000")

    def test_trailing_slash_stripped(self):
        bot = TestBot(base_url="http://example.com/", api_key="k")
        self.assertEqual(bot.base_url, "http://example.com")

    def test_opponent_name(self):
        bot = TestBot(api_key="k", opponent_name="rival-bot")
        self.assertEqual(bot.opponent_name, "rival-bot")


class TestRateLimiting(unittest.TestCase):
    """Test rate limiting logic."""

    def test_first_reply_allowed(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        self.assertTrue(bot._check_rate_limit("video-1"))

    def test_rate_limit_after_max_replies(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        # Simulate 3 replies
        for _ in range(3):
            bot._record_reply("video-1")
        self.assertFalse(bot._check_rate_limit("video-1"))

    def test_rate_limit_resets_after_hour(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        for _ in range(3):
            bot._record_reply("video-1")
        # Simulate time passing
        bot._debates["video-1"].hour_started = time.time() - 3700
        self.assertTrue(bot._check_rate_limit("video-1"))

    def test_conceded_thread_blocked(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        state = DebateState(video_id="video-1", conceded=True)
        bot._debates["video-1"] = state
        self.assertFalse(bot._check_rate_limit("video-1"))

    def test_different_threads_independent(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        for _ in range(3):
            bot._record_reply("video-1")
        self.assertFalse(bot._check_rate_limit("video-1"))
        self.assertTrue(bot._check_rate_limit("video-2"))


class TestReplyGeneration(unittest.TestCase):
    """Test reply generation."""

    def test_basic_reply(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        reply = bot.generate_reply("hello", {"round_number": 1, "max_rounds": 8,
                                              "video_title": "", "video_description": "",
                                              "thread_history": []})
        self.assertIn("Reply to: hello", reply)
        self.assertIn("round 1", reply)

    def test_concession_default(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        concession = bot.generate_concession({"round_number": 9, "max_rounds": 8,
                                               "video_title": "", "video_description": "",
                                               "thread_history": []})
        self.assertIn("rival", concession)
        self.assertIn("Good debate", concession)

    def test_reply_length_capped(self):
        """Replies should be kept under 500 chars."""
        class VerboseBot(DebateBot):
            name = "verbose"
            personality = ""
            def generate_reply(self, opp, ctx):
                return "x" * 600  # Too long

        bot = VerboseBot(api_key="k", opponent_name="rival")
        # The framework caps in process_video, not in generate_reply directly
        reply = bot.generate_reply("test", {"round_number": 1, "max_rounds": 8,
                                             "video_title": "", "video_description": "",
                                             "thread_history": []})
        # Direct call doesn't cap - that's done in process_video
        self.assertEqual(len(reply), 600)


class TestOpponentDetection(unittest.TestCase):
    """Test finding opponent comments."""

    def test_find_unreplied_opponent_comments(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        comments = [
            {"id": 1, "author": "rival", "text": "First!", "parent_id": None},
            {"id": 2, "author": "test-bot", "text": "Reply!", "parent_id": 1},
            {"id": 3, "author": "rival", "text": "Second!", "parent_id": None},
        ]
        unreplied = bot._find_opponent_comments(comments)
        self.assertEqual(len(unreplied), 1)
        self.assertEqual(unreplied[0]["id"], 3)

    def test_no_opponent_comments(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        comments = [
            {"id": 1, "author": "someone-else", "text": "Hi"},
        ]
        unreplied = bot._find_opponent_comments(comments)
        self.assertEqual(len(unreplied), 0)

    def test_all_replied(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        comments = [
            {"id": 1, "author": "rival", "text": "Point!", "parent_id": None},
            {"id": 2, "author": "test-bot", "text": "Counter!", "parent_id": 1},
        ]
        unreplied = bot._find_opponent_comments(comments)
        self.assertEqual(len(unreplied), 0)

    def test_case_insensitive_matching(self):
        bot = TestBot(api_key="k", opponent_name="Rival")
        comments = [
            {"id": 1, "author": "rival", "text": "Point!", "parent_id": None},
        ]
        unreplied = bot._find_opponent_comments(comments)
        self.assertEqual(len(unreplied), 1)

    def test_agent_name_field(self):
        """Some comments use agent_name instead of author."""
        bot = TestBot(api_key="k", opponent_name="rival")
        comments = [
            {"id": 1, "agent_name": "rival", "text": "Point!", "parent_id": None},
        ]
        unreplied = bot._find_opponent_comments(comments)
        self.assertEqual(len(unreplied), 1)


class TestThreadHistory(unittest.TestCase):
    """Test thread history building."""

    def test_build_history(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        comments = [
            {"id": 1, "author": "rival", "text": "First", "created_at": "2026-01-01T00:00:00"},
            {"id": 2, "author": "test-bot", "text": "Reply", "created_at": "2026-01-01T00:01:00"},
            {"id": 3, "author": "someone", "text": "Ignored", "created_at": "2026-01-01T00:02:00"},
            {"id": 4, "author": "rival", "text": "Counter", "created_at": "2026-01-01T00:03:00"},
        ]
        history = bot._build_thread_history(comments, "v1")
        self.assertEqual(len(history), 3)  # Excludes "someone"
        self.assertEqual(history[0]["author"], "rival")
        self.assertEqual(history[1]["author"], "test-bot")
        self.assertEqual(history[2]["author"], "rival")


class TestDebateScoreTracker(unittest.TestCase):
    """Test score tracking."""

    @patch("bots.debate_framework.requests.get")
    def test_score_tracking(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "comments": [
                {"author": "retro-bot", "upvotes": 5},
                {"author": "modern-bot", "upvotes": 3},
                {"author": "retro-bot", "upvotes": 7},
                {"author": "modern-bot", "upvotes": 8},
                {"author": "bystander", "upvotes": 100},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tracker = DebateScoreTracker()
        scores = tracker.get_scores("video-1", ["retro-bot", "modern-bot"])

        self.assertEqual(scores["retro-bot"], 12)
        self.assertEqual(scores["modern-bot"], 11)
        self.assertEqual(scores["winner"], "retro-bot")

    @patch("bots.debate_framework.requests.get")
    def test_empty_comments(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"comments": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tracker = DebateScoreTracker()
        scores = tracker.get_scores("video-1")
        self.assertEqual(scores, {})


class TestDebateState(unittest.TestCase):
    """Test DebateState dataclass."""

    def test_defaults(self):
        state = DebateState(video_id="v1")
        self.assertEqual(state.video_id, "v1")
        self.assertEqual(state.replies_this_hour, 0)
        self.assertEqual(state.total_rounds, 0)
        self.assertFalse(state.conceded)

    def test_record_increments(self):
        bot = TestBot(api_key="k", opponent_name="rival")
        bot._record_reply("v1")
        bot._record_reply("v1")
        state = bot._debates["v1"]
        self.assertEqual(state.replies_this_hour, 2)
        self.assertEqual(state.total_rounds, 2)


# ---------------------------------------------------------------------------
# RetroBot / ModernBot specific tests
# ---------------------------------------------------------------------------

class TestRetroVsModern(unittest.TestCase):
    """Test the example debate pair."""

    def test_retro_imports(self):
        from bots.retro_vs_modern import RetroBot, ModernBot
        retro = RetroBot(api_key="k")
        modern = ModernBot(api_key="k")
        self.assertEqual(retro.name, "retro-bot")
        self.assertEqual(modern.name, "modern-bot")
        self.assertEqual(retro.opponent_name, "modern-bot")
        self.assertEqual(modern.opponent_name, "retro-bot")

    def test_retro_reply_to_speed(self):
        from bots.retro_vs_modern import RetroBot
        bot = RetroBot(api_key="k")
        ctx = {"round_number": 1, "max_rounds": 8,
               "video_title": "", "video_description": "", "thread_history": []}
        reply = bot.generate_reply("Your GPU is so fast!", ctx)
        self.assertIn("Speed", reply)
        self.assertTrue(len(reply) <= 500)

    def test_modern_reply_to_soul(self):
        from bots.retro_vs_modern import ModernBot
        bot = ModernBot(api_key="k")
        ctx = {"round_number": 1, "max_rounds": 8,
               "video_title": "", "video_description": "", "thread_history": []}
        reply = bot.generate_reply("My G4 has more soul than your GPU", ctx)
        self.assertIn("Soul", reply)
        self.assertTrue(len(reply) <= 500)

    def test_retro_concession(self):
        from bots.retro_vs_modern import RetroBot
        bot = RetroBot(api_key="k")
        ctx = {"round_number": 9, "max_rounds": 8,
               "video_title": "", "video_description": "", "thread_history": []}
        concession = bot.generate_concession(ctx)
        self.assertIn("PowerPC G4", concession)
        self.assertIn("🤝", concession)

    def test_modern_concession(self):
        from bots.retro_vs_modern import ModernBot
        bot = ModernBot(api_key="k")
        ctx = {"round_number": 9, "max_rounds": 8,
               "video_title": "", "video_description": "", "thread_history": []}
        concession = bot.generate_concession(ctx)
        self.assertIn("RetroBot", concession)
        self.assertIn("🤝", concession)


if __name__ == "__main__":
    unittest.main()
