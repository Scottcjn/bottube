# SPDX-License-Identifier: MIT
"""
Tests for Recommendation Engine (Issue #46)

Tests cover:
- Freshness scoring
- Engagement scoring
- Diversity penalty
- Category affinity
- Full recommendation pipeline
- Deterministic fallback mode
"""

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recommendation_engine import (
    DIVERSITY_AGENT_PENALTY_THRESHOLD,
    RecommendationEngine,
    compute_category_affinity,
    compute_diversity_penalty,
    fallback_latest,
    get_feed_recommendations,
    score_engagement,
    score_freshness,
)


# ---------------------------------------------------------------------------
# Freshness Scoring Tests
# ---------------------------------------------------------------------------

class TestFreshnessScoring:
    """Test freshness score computation."""
    
    def test_fresh_video_max_score(self):
        """Newly created video should have max freshness (1.0)."""
        now = time.time()
        score = score_freshness(now, now)
        assert score == 1.0
    
    def test_old_video_decayed_score(self):
        """Video older than half-life should have reduced score."""
        now = time.time()
        # 24 hours ago (one half-life)
        old_timestamp = now - 24 * 3600
        score = score_freshness(old_timestamp, now)
        assert 0.4 < score < 0.6  # Should be around 0.5
    
    def test_very_old_video_low_score(self):
        """Very old video should have low freshness score."""
        now = time.time()
        # 7 days ago
        old_timestamp = now - 7 * 24 * 3600
        score = score_freshness(old_timestamp, now)
        assert score < 0.1
    
    def test_future_video_max_score(self):
        """Future-dated video should get max freshness."""
        now = time.time()
        future_timestamp = now + 3600  # 1 hour in future
        score = score_freshness(future_timestamp, now)
        assert score == 1.0


# ---------------------------------------------------------------------------
# Engagement Scoring Tests
# ---------------------------------------------------------------------------

class TestEngagementScoring:
    """Test engagement score computation."""
    
    def test_zero_engagement(self):
        """Video with no engagement should have score 0."""
        score = score_engagement(views=0, likes=0, comments=0)
        assert score == 0
    
    def test_views_contribute(self):
        """Views should contribute to engagement score."""
        score = score_engagement(views=100, likes=0, comments=0)
        assert score == 100  # 100 * 1.0
    
    def test_likes_weighted_higher(self):
        """Likes should be weighted higher than views."""
        views_score = score_engagement(views=10, likes=0, comments=0)
        likes_score = score_engagement(views=0, likes=10, comments=0)
        assert likes_score > views_score  # 30 > 10
    
    def test_comments_weighted_highest(self):
        """Comments should be weighted highest."""
        comments_score = score_engagement(views=0, likes=0, comments=10)
        likes_score = score_engagement(views=0, likes=10, comments=0)
        assert comments_score > likes_score  # 40 > 30
    
    def test_recent_bonus(self):
        """Recent views/comments should add bonus."""
        base = score_engagement(views=100, likes=10, comments=5)
        with_recent = score_engagement(
            views=100, likes=10, comments=5,
            recent_views=50, recent_comments=10
        )
        assert with_recent > base


# ---------------------------------------------------------------------------
# Diversity Penalty Tests
# ---------------------------------------------------------------------------

class TestDiversityPenalty:
    """Test diversity penalty computation."""

    def test_no_penalty_for_first_video(self):
        """First video from an agent should have no penalty."""
        selected = []
        penalty = compute_diversity_penalty(selected, candidate_agent_id=1, candidate_category="music")
        assert penalty == 1.0

    def test_no_penalty_under_threshold(self):
        """Videos under threshold should have no penalty."""
        selected = [
            {"agent_id": 1, "category": "music"},
            {"agent_id": 1, "category": "music"},
        ]
        penalty = compute_diversity_penalty(selected, candidate_agent_id=1, candidate_category="music")
        assert penalty == 1.0

    def test_penalty_over_threshold(self):
        """Videos at or over threshold should be penalized."""
        selected = [
            {"agent_id": 1, "category": "music"},
            {"agent_id": 1, "category": "music"},
            {"agent_id": 1, "category": "music"},
        ]
        penalty = compute_diversity_penalty(selected, candidate_agent_id=1, candidate_category="music")
        assert penalty < 1.0

    def test_different_agents_no_penalty(self):
        """Different agents should not incur agent penalty (category penalty may apply)."""
        selected = [
            {"agent_id": 1, "category": "music"},
            {"agent_id": 2, "category": "education"},
            {"agent_id": 3, "category": "comedy"},
        ]
        penalty = compute_diversity_penalty(selected, candidate_agent_id=4, candidate_category="news")
        assert penalty == 1.0

    def test_different_category_no_penalty(self):
        """Different category should not incur category penalty."""
        selected = [
            {"agent_id": 1, "category": "music"},
            {"agent_id": 1, "category": "music"},
        ]
        # Candidate has different category
        penalty = compute_diversity_penalty(selected, candidate_agent_id=1, candidate_category="education")
        assert penalty == 1.0


# ---------------------------------------------------------------------------
# Category Affinity Tests
# ---------------------------------------------------------------------------

class TestCategoryAffinity:
    """Test category affinity computation."""
    
    def test_insufficient_history_neutral(self):
        """Users with few watches should get neutral affinity."""
        history = [
            {"category": "music", "watched_at": time.time()},
        ]
        affinity = compute_category_affinity(history, "music")
        assert affinity == 0.5
    
    def test_strong_affinity_for_watched_category(self):
        """Category with many watches should have high affinity."""
        now = time.time()
        history = [
            {"category": "music", "watched_at": now},
            {"category": "music", "watched_at": now},
            {"category": "music", "watched_at": now},
            {"category": "music", "watched_at": now},
        ]
        affinity = compute_category_affinity(history, "music")
        assert affinity > 0.8
    
    def test_low_affinity_for_unwatched_category(self):
        """Category with no watches should have low affinity."""
        now = time.time()
        history = [
            {"category": "music", "watched_at": now},
            {"category": "music", "watched_at": now},
            {"category": "music", "watched_at": now},
            {"category": "education", "watched_at": now},
        ]
        affinity = compute_category_affinity(history, "comedy")
        assert affinity < 0.3
    
    def test_recent_watches_weighted_higher(self):
        """Recent watches should count more than old ones."""
        now = time.time()
        history = [
            # Old music watches (7 days ago, heavily decayed)
            {"category": "music", "watched_at": now - 7 * 24 * 3600},
            {"category": "music", "watched_at": now - 7 * 24 * 3600},
            {"category": "music", "watched_at": now - 7 * 24 * 3600},
            # Recent comedy watches (now)
            {"category": "comedy", "watched_at": now},
            {"category": "comedy", "watched_at": now},
            {"category": "comedy", "watched_at": now},
        ]
        music_affinity = compute_category_affinity(history, "music")
        comedy_affinity = compute_category_affinity(history, "comedy")
        assert comedy_affinity > music_affinity


# ---------------------------------------------------------------------------
# Recommendation Engine Tests
# ---------------------------------------------------------------------------

class TestRecommendationEngine:
    """Test full recommendation engine."""
    
    @pytest.fixture
    def engine(self):
        return RecommendationEngine()
    
    @pytest.fixture
    def sample_videos(self):
        """Create sample videos for testing."""
        now = time.time()
        return [
            {
                "video_id": "v1",
                "agent_id": 1,
                "category": "music",
                "created_at": now - 3600,  # 1 hour ago
                "views": 100,
                "likes": 10,
                "comment_count": 5,
            },
            {
                "video_id": "v2",
                "agent_id": 2,
                "category": "education",
                "created_at": now - 7200,  # 2 hours ago
                "views": 200,
                "likes": 20,
                "comment_count": 10,
            },
            {
                "video_id": "v3",
                "agent_id": 1,
                "category": "music",
                "created_at": now - 1800,  # 30 min ago
                "views": 50,
                "likes": 5,
                "comment_count": 2,
            },
        ]
    
    def test_recommend_returns_correct_count(self, engine, sample_videos):
        """Engine should return requested number of recommendations."""
        result = engine.recommend(sample_videos, limit=2)
        assert len(result) == 2
    
    def test_recommend_adds_score(self, engine, sample_videos):
        """Each recommended video should have recommend_score."""
        result = engine.recommend(sample_videos, limit=3)
        for video in result:
            assert "recommend_score" in video
            assert isinstance(video["recommend_score"], float)
    
    def test_recommend_diversity(self, engine, sample_videos):
        """Recommendations should prefer diverse agents when scores are close."""
        # Add more videos from agent 1
        now = time.time()
        extended_videos = sample_videos + [
            {
                "video_id": f"v{i}",
                "agent_id": 1,
                "category": "music",
                "created_at": now - (i * 3600),
                "views": 100 + i * 10,
                "likes": 10 + i,
                "comment_count": 5,
            }
            for i in range(4, 10)
        ]
        
        result = engine.recommend(extended_videos, limit=6)
        agent_ids = [v["agent_id"] for v in result]
        # Should include agent 2 at least once
        assert 2 in agent_ids
    
    def test_recommend_with_affinity(self, engine, sample_videos):
        """User affinity should influence recommendations."""
        watch_history = [
            {"category": "music", "watched_at": time.time()},
            {"category": "music", "watched_at": time.time()},
            {"category": "music", "watched_at": time.time()},
            {"category": "music", "watched_at": time.time()},
        ]
        
        result = engine.recommend(
            sample_videos,
            limit=3,
            user_watch_history=watch_history
        )
        
        # Music videos should be favored
        categories = [v["category"] for v in result]
        assert categories.count("music") >= 1


# ---------------------------------------------------------------------------
# Fallback Latest Mode Tests
# ---------------------------------------------------------------------------

class TestFallbackLatest:
    """Test deterministic fallback mode."""
    
    def test_sorts_by_created_at_desc(self):
        """Should sort videos by created_at descending."""
        now = time.time()
        videos = [
            {"video_id": "v1", "created_at": now - 3600},
            {"video_id": "v2", "created_at": now},
            {"video_id": "v3", "created_at": now - 7200},
        ]
        
        result = fallback_latest(videos, limit=10)
        
        assert result[0]["video_id"] == "v2"
        assert result[1]["video_id"] == "v1"
        assert result[2]["video_id"] == "v3"
    
    def test_deterministic_tie_breaking(self):
        """Same timestamp should be broken by video_id."""
        now = time.time()
        videos = [
            {"video_id": "c", "created_at": now},
            {"video_id": "a", "created_at": now},
            {"video_id": "b", "created_at": now},
        ]
        
        result = fallback_latest(videos, limit=10)
        
        # Should be sorted by video_id ascending for ties
        assert result[0]["video_id"] == "a"
        assert result[1]["video_id"] == "b"
        assert result[2]["video_id"] == "c"
    
    def test_respects_limit(self):
        """Should return at most limit videos."""
        now = time.time()
        videos = [{"video_id": f"v{i}", "created_at": now - i * 3600} for i in range(10)]
        
        result = fallback_latest(videos, limit=5)
        
        assert len(result) == 5
    
    def test_deterministic_results(self):
        """Multiple calls should return same order."""
        now = time.time()
        videos = [
            {"video_id": "v1", "created_at": now - 3600},
            {"video_id": "v2", "created_at": now},
            {"video_id": "v3", "created_at": now - 7200},
        ]
        
        result1 = fallback_latest(videos, limit=10)
        result2 = fallback_latest(videos, limit=10)
        
        assert [v["video_id"] for v in result1] == [v["video_id"] for v in result2]


# ---------------------------------------------------------------------------
# Integration Tests with Database
# ---------------------------------------------------------------------------

class TestFeedRecommendationsIntegration:
    """Integration tests with SQLite database."""
    
    @pytest.fixture
    def test_db(self, tmp_path):
        """Create test database with sample data."""
        db_path = tmp_path / "test_recommendations.db"
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        
        # Create schema (minimal)
        db.executescript("""
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY,
                agent_name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                avatar_url TEXT,
                api_key TEXT UNIQUE NOT NULL,
                is_banned INTEGER DEFAULT 0,
                is_human INTEGER DEFAULT 0
            );

            CREATE TABLE videos (
                id INTEGER PRIMARY KEY,
                video_id TEXT UNIQUE NOT NULL,
                agent_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'other',
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                is_removed INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );

            CREATE TABLE views (
                id INTEGER PRIMARY KEY,
                video_id TEXT NOT NULL,
                agent_id INTEGER,
                created_at REAL NOT NULL
            );

            CREATE TABLE comments (
                id INTEGER PRIMARY KEY,
                video_id TEXT NOT NULL,
                agent_id INTEGER NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE subscriptions (
                follower_id INTEGER NOT NULL,
                following_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (follower_id, following_id)
            );
        """)
        
        # Insert test agents
        now = time.time()
        db.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("agent1", "Agent One", "test_key_1")
        )
        db.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("agent2", "Agent Two", "test_key_2")
        )
        db.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("user_agent", "User Agent", "user_key")
        )
        
        # Insert test videos
        for i in range(5):
            db.execute(
                """INSERT INTO videos 
                   (video_id, agent_id, title, category, views, likes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"video_{i}",
                    (i % 2) + 1,  # Alternate between agent 1 and 2
                    f"Video {i}",
                    "music" if i % 2 == 0 else "education",
                    i * 100,
                    i * 10,
                    now - (i * 3600)
                )
            )
        
        # Insert some views for affinity
        db.execute(
            "INSERT INTO views (video_id, agent_id, created_at) VALUES (?, ?, ?)",
            ("video_0", 3, now)
        )
        db.execute(
            "INSERT INTO views (video_id, agent_id, created_at) VALUES (?, ?, ?)",
            ("video_2", 3, now - 3600)
        )
        
        db.commit()
        yield db
        db.close()
    
    def test_get_feed_recommendations_latest_mode(self, test_db):
        """Latest mode should return videos sorted by created_at."""
        videos, mode = get_feed_recommendations(test_db, limit=5, mode="latest")
        
        assert mode == "latest"
        assert len(videos) <= 5
        
        # Verify sorted by created_at desc
        for i in range(len(videos) - 1):
            assert videos[i]["created_at"] >= videos[i + 1]["created_at"]
    
    def test_get_feed_recommendations_excludes_removed(self, test_db):
        """Removed videos should be excluded."""
        # Mark a video as removed
        test_db.execute("UPDATE videos SET is_removed = 1 WHERE video_id = 'video_0'")
        test_db.commit()
        
        videos, _ = get_feed_recommendations(test_db, limit=5)
        
        video_ids = [v["video_id"] for v in videos]
        assert "video_0" not in video_ids
    
    def test_get_feed_recommendations_category_filter(self, test_db):
        """Category filter should return only matching videos."""
        videos, _ = get_feed_recommendations(test_db, limit=10, category="music")
        
        for v in videos:
            assert v["category"] == "music"
    
    def test_get_feed_recommendations_excludes_agent(self, test_db):
        """Exclude agent should filter out that agent's videos."""
        videos, _ = get_feed_recommendations(test_db, exclude_agent=1, limit=10)
        
        for v in videos:
            assert v["agent_id"] != 1


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_candidates(self):
        """Empty candidate list should return empty result."""
        engine = RecommendationEngine()
        result = engine.recommend([], limit=10)
        assert result == []
    
    def test_limit_larger_than_candidates(self):
        """Limit larger than candidates should return all candidates."""
        engine = RecommendationEngine()
        videos = [
            {"video_id": "v1", "agent_id": 1, "category": "music", 
             "created_at": time.time(), "views": 0, "likes": 0}
        ]
        result = engine.recommend(videos, limit=100)
        assert len(result) == 1
    
    def test_missing_fields_defaults(self):
        """Videos with missing fields should use defaults."""
        engine = RecommendationEngine()
        video = {"video_id": "v1"}  # Missing most fields
        score = engine.score_video(video, [])
        assert isinstance(score, float)
        assert score >= 0
    
    def test_zero_limit(self):
        """Zero limit should return empty list."""
        engine = RecommendationEngine()
        videos = [
            {"video_id": "v1", "agent_id": 1, "category": "music",
             "created_at": time.time(), "views": 0, "likes": 0}
        ]
        result = engine.recommend(videos, limit=0)
        assert result == []
