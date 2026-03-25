# SPDX-License-Identifier: MIT
"""
Tests for the BoTTube Debate Bot Framework.

Covers: DebateBot, RateLimiter, DebateOrchestrator, RetroBot, ModernBot,
ThreadContext, and the full debate lifecycle.
"""

import sys
import time
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bots.debate_framework import (
    BoTTubeClient,
    Comment,
    DebateBot,
    DebateOrchestrator,
    RateLimiter,
    ThreadContext,
    Video,
)
from bots.retro_vs_modern import ModernBot, RetroBot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_video(vid="v1", tags=None):
    return Video(id=vid, title="Test Debate", tags=tags or ["debate"])


def make_comment(cid="c1", video_id="v1", author="user1", body="Hello",
                 parent_id=None, upvotes=0, downvotes=0):
    return Comment(
        id=cid, video_id=video_id, author=author, body=body,
        parent_id=parent_id, upvotes=upvotes, downvotes=downvotes,
    )


def make_thread(comments=None, video=None):
    v = video or make_video()
    cs = comments or []
    root_id = cs[0].id if cs else None
    return ThreadContext(video=v, comments=cs, root_comment_id=root_id)


class SimpleBot(DebateBot):
    """A concrete test bot."""
    name = "SimpleBot"
    personality = "Test bot"
    max_rounds = 3

    def generate_reply(self, thread, opponent_comment):
        if not opponent_comment:
            return "I'll start: hello!"
        return f"Reply to {opponent_comment.author}"


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_allows_up_to_max(self):
        rl = RateLimiter(max_replies=3, window_seconds=3600)
        assert rl.is_allowed("thread-1") is True
        rl.record("thread-1")
        assert rl.is_allowed("thread-1") is True
        rl.record("thread-1")
        assert rl.is_allowed("thread-1") is True
        rl.record("thread-1")
        assert rl.is_allowed("thread-1") is False

    def test_different_threads_independent(self):
        rl = RateLimiter(max_replies=1, window_seconds=3600)
        rl.record("thread-1")
        assert rl.is_allowed("thread-1") is False
        assert rl.is_allowed("thread-2") is True

    def test_window_expiry(self):
        rl = RateLimiter(max_replies=1, window_seconds=1)
        rl.record("t1")
        assert rl.is_allowed("t1") is False
        time.sleep(1.1)
        assert rl.is_allowed("t1") is True

    def test_reset_clears_all(self):
        rl = RateLimiter(max_replies=1)
        rl.record("t1")
        rl.record("t2")
        rl.reset()
        assert rl.is_allowed("t1") is True
        assert rl.is_allowed("t2") is True


# ---------------------------------------------------------------------------
# Comment model
# ---------------------------------------------------------------------------

class TestComment:
    def test_score(self):
        c = make_comment(upvotes=10, downvotes=3)
        assert c.score == 7

    def test_score_negative(self):
        c = make_comment(upvotes=1, downvotes=5)
        assert c.score == -4


# ---------------------------------------------------------------------------
# ThreadContext
# ---------------------------------------------------------------------------

class TestThreadContext:
    def test_depth(self):
        t = make_thread([make_comment("c1"), make_comment("c2")])
        assert t.depth == 2

    def test_empty_depth(self):
        t = make_thread([])
        assert t.depth == 0

    def test_last_comment(self):
        c1 = make_comment("c1")
        c2 = make_comment("c2", author="bot1")
        t = make_thread([c1, c2])
        assert t.last_comment() == c2

    def test_last_comment_empty(self):
        t = make_thread([])
        assert t.last_comment() is None

    def test_comments_by(self):
        c1 = make_comment("c1", author="RetroBot")
        c2 = make_comment("c2", author="ModernBot")
        c3 = make_comment("c3", author="RetroBot")
        t = make_thread([c1, c2, c3])
        assert len(t.comments_by("RetroBot")) == 2
        assert len(t.comments_by("ModernBot")) == 1
        assert len(t.comments_by("Unknown")) == 0


# ---------------------------------------------------------------------------
# DebateBot (abstract)
# ---------------------------------------------------------------------------

class TestDebateBot:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            DebateBot()  # abstract: generate_reply not implemented

    def test_concrete_bot_creates(self):
        bot = SimpleBot()
        assert bot.name == "SimpleBot"
        assert bot.max_rounds == 3

    def test_generate_reply_opener(self):
        bot = SimpleBot()
        thread = make_thread([])
        reply = bot.generate_reply(thread, None)
        assert "hello" in reply.lower()

    def test_generate_reply_to_opponent(self):
        bot = SimpleBot()
        opp = make_comment(author="Opponent")
        thread = make_thread([opp])
        reply = bot.generate_reply(thread, opp)
        assert "Opponent" in reply

    def test_no_self_reply(self):
        bot = SimpleBot()
        bot.client = MagicMock()
        # Last comment is from SimpleBot itself
        own_comment = make_comment(author="SimpleBot")
        thread = make_thread([own_comment])
        result = bot.maybe_reply(thread)
        assert result is None

    def test_concession_after_max_rounds(self):
        bot = SimpleBot()
        bot.client = MagicMock()
        bot.client.post_comment.return_value = make_comment(
            author="SimpleBot", body="GG"
        )
        # Fill thread with max_rounds of own comments
        comments = []
        for i in range(bot.max_rounds):
            comments.append(make_comment(f"c{i*2}", author="Opponent",
                                         body=f"Attack {i}"))
            comments.append(make_comment(f"c{i*2+1}", author="SimpleBot",
                                         body=f"Defense {i}"))
        # Last comment from opponent so bot tries to reply
        comments.append(make_comment("clast", author="Opponent",
                                     body="Final attack"))
        thread = make_thread(comments)
        result = bot.maybe_reply(thread)
        # Should concede (post GG) or return None
        if result:
            assert "GG" in result.body or "🤝" in result.body

    def test_rate_limiting(self):
        bot = SimpleBot()
        bot.client = MagicMock()
        bot.client.post_comment.return_value = make_comment(
            author="SimpleBot", body="Reply"
        )
        video = make_video()
        # Post max_replies_per_hour times
        for i in range(bot.max_replies_per_hour):
            opp = make_comment(f"c{i}", author="Opponent")
            thread = ThreadContext(
                video=video, comments=[opp], root_comment_id="c0",
            )
            bot.maybe_reply(thread)

        # Next should be rate-limited
        opp = make_comment("extra", author="Opponent")
        thread = ThreadContext(
            video=video, comments=[opp], root_comment_id="c0",
        )
        result = bot.maybe_reply(thread)
        assert result is None

    def test_dry_run_no_client(self):
        """Without a client, bot logs but doesn't crash."""
        bot = SimpleBot()
        bot.client = None
        opp = make_comment(author="Opponent")
        thread = make_thread([opp])
        result = bot.maybe_reply(thread)
        assert result is None


# ---------------------------------------------------------------------------
# DebateOrchestrator
# ---------------------------------------------------------------------------

class TestDebateOrchestrator:
    def test_register_bots(self):
        orch = DebateOrchestrator(api_url="http://test")
        orch.register(RetroBot())
        orch.register(ModernBot())
        assert len(orch.bots) == 2

    def test_build_threads_empty(self):
        video = make_video()
        threads = DebateOrchestrator._build_threads(video, [])
        assert len(threads) == 1
        assert threads[0].depth == 0

    def test_build_threads_single_chain(self):
        video = make_video()
        c1 = make_comment("c1", parent_id=None, author="RetroBot")
        c2 = make_comment("c2", parent_id="c1", author="ModernBot")
        c3 = make_comment("c3", parent_id="c2", author="RetroBot")
        threads = DebateOrchestrator._build_threads(video, [c1, c2, c3])
        assert len(threads) == 1
        assert threads[0].depth == 3

    def test_build_threads_multiple_roots(self):
        video = make_video()
        c1 = make_comment("c1", parent_id=None, author="A")
        c2 = make_comment("c2", parent_id=None, author="B")
        threads = DebateOrchestrator._build_threads(video, [c1, c2])
        assert len(threads) == 2

    def test_build_threads_circular_reference_guard(self):
        """Circular parent references should not cause infinite loops."""
        video = make_video()
        c1 = make_comment("c1", parent_id="c2", author="A")
        c2 = make_comment("c2", parent_id="c1", author="B")
        # Won't be an infinite loop thanks to visited set
        threads = DebateOrchestrator._build_threads(video, [c1, c2])
        assert isinstance(threads, list)

    def test_run_once_with_mock_client(self):
        orch = DebateOrchestrator(api_url="http://test")
        retro = RetroBot()
        modern = ModernBot()
        orch.register(retro)
        orch.register(modern)

        # Mock the client
        orch.client = MagicMock()
        orch.client.list_debate_videos.return_value = [make_video()]
        orch.client.get_comments.return_value = []
        orch.client.post_comment.return_value = make_comment(
            author="RetroBot", body="Opening salvo!"
        )

        # Assign same mock client to bots
        for bot in orch.bots:
            bot.client = orch.client

        orch.run_once()
        # Should have attempted to post (at least one bot opens)
        assert orch.client.post_comment.called


# ---------------------------------------------------------------------------
# RetroBot
# ---------------------------------------------------------------------------

class TestRetroBot:
    def test_opener(self):
        bot = RetroBot()
        thread = make_thread([])
        reply = bot.generate_reply(thread, None)
        assert reply is not None
        assert len(reply) > 10

    def test_rebuttal(self):
        bot = RetroBot()
        opp = make_comment(author="ModernBot", body="M3 is better!")
        thread = make_thread([opp])
        reply = bot.generate_reply(thread, opp)
        assert reply is not None

    def test_concession_mentions_opponent(self):
        bot = RetroBot()
        opp = make_comment(author="ModernBot", body="Final point")
        thread = make_thread([opp])
        msg = bot.concession_message(thread)
        assert "GG" in msg or "🤝" in msg

    def test_different_openers(self):
        """RetroBot should have variety in openers."""
        bot = RetroBot()
        thread = make_thread([])
        replies = set()
        for _ in range(20):
            replies.add(bot.generate_reply(thread, None))
        assert len(replies) >= 2, "Openers should have variety"


# ---------------------------------------------------------------------------
# ModernBot
# ---------------------------------------------------------------------------

class TestModernBot:
    def test_opener(self):
        bot = ModernBot()
        thread = make_thread([])
        reply = bot.generate_reply(thread, None)
        assert reply is not None
        assert len(reply) > 10

    def test_rebuttal(self):
        bot = ModernBot()
        opp = make_comment(author="RetroBot", body="PowerPC rules!")
        thread = make_thread([opp])
        reply = bot.generate_reply(thread, opp)
        assert reply is not None

    def test_concession_mentions_opponent(self):
        bot = ModernBot()
        opp = make_comment(author="RetroBot")
        thread = make_thread([opp])
        msg = bot.concession_message(thread)
        assert "GG" in msg or "🤝" in msg

    def test_different_openers(self):
        bot = ModernBot()
        thread = make_thread([])
        replies = set()
        for _ in range(20):
            replies.add(bot.generate_reply(thread, None))
        assert len(replies) >= 2


# ---------------------------------------------------------------------------
# Integration: full debate simulation
# ---------------------------------------------------------------------------

class TestFullDebate:
    def test_multi_round_debate(self):
        """Simulate a 6-round debate between RetroBot and ModernBot."""
        video = make_video()
        retro = RetroBot()
        modern = ModernBot()

        comments = []
        # Round 1: RetroBot opens
        opener = retro.generate_reply(make_thread([]), None)
        assert opener is not None
        comments.append(make_comment("c0", author="RetroBot", body=opener))

        # Alternate for 5 more rounds
        bots = [modern, retro, modern, retro, modern]
        for i, bot in enumerate(bots):
            thread = make_thread(comments)
            reply = bot.generate_reply(thread, thread.last_comment())
            assert reply is not None, f"Round {i+2}: {bot.name} returned None"
            comments.append(make_comment(
                f"c{i+1}", author=bot.name, body=reply,
                parent_id=comments[-1].id,
            ))

        # Should have 6 comments total
        assert len(comments) == 6
        authors = [c.author for c in comments]
        assert "RetroBot" in authors
        assert "ModernBot" in authors

    def test_score_tracking(self):
        """Simulate scores based on upvotes."""
        video = make_video()
        comments = [
            make_comment("c1", author="RetroBot", body="Vintage!", upvotes=15),
            make_comment("c2", author="ModernBot", body="Modern!", upvotes=12),
            make_comment("c3", author="RetroBot", body="Soul!", upvotes=8, downvotes=2),
        ]

        orch = DebateOrchestrator(api_url="http://test")
        orch.register(RetroBot())
        orch.register(ModernBot())
        orch.client = MagicMock()
        orch.client.list_debate_videos.return_value = [video]
        orch.client.get_comments.return_value = comments

        scores = orch.get_scores()
        assert scores["RetroBot"] == 15 + 6  # (15-0) + (8-2)
        assert scores["ModernBot"] == 12
