# SPDX-License-Identifier: MIT
"""
Tests for BoTTube Thumbnail & CTR Tracking System

Covers:
- best_frame: Frame scoring functions
- ctr_tracker: Impression/click/watch_time recording, queries
- ab_test: Variant management, serving, winner detection
- ranking_signal: Feed score computation, phase weighting
"""

import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from thumbnails.best_frame import (
    score_brightness,
    score_contrast,
    score_edge_density,
    score_frame,
    select_best_frame,
)
from thumbnails.ctr_tracker import CTRTracker
from thumbnails.ab_test import ABTestManager, MIN_IMPRESSIONS_PER_VARIANT
from thumbnails.ranking_signal import (
    EARLY_HOURS,
    compute_feed_score,
    integrate_with_feed,
    _recency_score,
    _phase_weights,
    _engagement_score,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db():
    """Create a temporary SQLite database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test.db")


@pytest.fixture
def tracker(tmp_db):
    """Initialized CTRTracker."""
    t = CTRTracker(tmp_db)
    t.init_db()
    return t


@pytest.fixture
def ab_manager(tmp_db):
    """Initialized ABTestManager."""
    m = ABTestManager(tmp_db)
    m.init_db()
    return m


# ---------------------------------------------------------------------------
# best_frame: scoring
# ---------------------------------------------------------------------------

class TestBestFrameScoring:
    """Test frame quality scoring functions."""

    def test_brightness_ideal(self):
        """Mid-brightness pixels should score near 1.0."""
        pixels = np.full((100, 100), 130, dtype=np.uint8)
        score = score_brightness(pixels)
        assert score > 0.9

    def test_brightness_too_dark(self):
        """Very dark pixels should score low."""
        pixels = np.full((100, 100), 10, dtype=np.uint8)
        score = score_brightness(pixels)
        assert score < 0.3

    def test_brightness_too_bright(self):
        """Very bright pixels should score low."""
        pixels = np.full((100, 100), 250, dtype=np.uint8)
        score = score_brightness(pixels)
        assert score < 0.3

    def test_contrast_high(self):
        """High contrast image should score well."""
        pixels = np.zeros((100, 100), dtype=np.uint8)
        pixels[:50, :] = 200
        pixels[50:, :] = 20
        score = score_contrast(pixels)
        assert score > 0.5

    def test_contrast_flat(self):
        """Flat image should score near zero."""
        pixels = np.full((100, 100), 128, dtype=np.uint8)
        score = score_contrast(pixels)
        assert score < 0.05

    def test_edge_density_detailed(self):
        """Image with lots of edges should score high."""
        gray = np.random.randint(0, 256, (100, 100), dtype=np.uint8)
        score = score_edge_density(gray)
        assert score > 0.3

    def test_edge_density_flat(self):
        """Flat image should have near-zero edge density."""
        gray = np.full((100, 100), 128, dtype=np.uint8)
        score = score_edge_density(gray)
        assert score < 0.01

    def test_edge_density_tiny_image(self):
        """Tiny image (< 3px) should return 0."""
        gray = np.array([[100, 200]], dtype=np.uint8)
        score = score_edge_density(gray)
        assert score == 0.0


# ---------------------------------------------------------------------------
# ctr_tracker
# ---------------------------------------------------------------------------

class TestCTRTracker:
    """Test CTR tracking and queries."""

    def test_record_impression(self, tracker):
        """Recording an impression should increment the count."""
        tracker.record_impression("vid1")
        stats = tracker.get_stats("vid1")
        assert stats is not None
        assert stats["impressions"] == 1
        assert stats["clicks"] == 0

    def test_record_click(self, tracker):
        """Recording a click should increment click count."""
        tracker.record_impression("vid1")
        tracker.record_click("vid1")
        stats = tracker.get_stats("vid1")
        assert stats["clicks"] == 1

    def test_ctr_computation(self, tracker):
        """CTR should be clicks / impressions."""
        for _ in range(10):
            tracker.record_impression("vid1")
        for _ in range(3):
            tracker.record_click("vid1")
        stats = tracker.get_stats("vid1")
        assert abs(stats["ctr"] - 0.3) < 0.001

    def test_watch_time_accumulation(self, tracker):
        """Watch time should accumulate across multiple records."""
        tracker.record_click("vid1")
        tracker.record_watch_time("vid1", 10.0)
        tracker.record_watch_time("vid1", 15.0)
        stats = tracker.get_stats("vid1")
        assert abs(stats["watch_time_sum"] - 25.0) < 0.01
        assert abs(stats["avg_watch_time"] - 25.0) < 0.01  # 25/1 click

    def test_batch_impressions(self, tracker):
        """Batch impression recording should work for multiple videos."""
        tracker.record_impressions_batch(["a", "b", "c", "a"])
        sa = tracker.get_stats("a")
        sb = tracker.get_stats("b")
        assert sa["impressions"] == 2
        assert sb["impressions"] == 1

    def test_top_by_ctr(self, tracker):
        """get_top_by_ctr should rank by CTR with min impression filter."""
        # vid_high: 5/10 = 50% CTR
        for _ in range(10):
            tracker.record_impression("vid_high")
        for _ in range(5):
            tracker.record_click("vid_high")
        # vid_low: 1/10 = 10% CTR
        for _ in range(10):
            tracker.record_impression("vid_low")
        tracker.record_click("vid_low")

        top = tracker.get_top_by_ctr(limit=10, min_impressions=5)
        assert len(top) == 2
        assert top[0]["video_id"] == "vid_high"

    def test_underperforming(self, tracker):
        """get_underperforming should find low-CTR videos."""
        for _ in range(100):
            tracker.record_impression("vid_bad")
        tracker.record_click("vid_bad")  # 1% CTR
        results = tracker.get_underperforming(min_impressions=50, max_ctr=0.02)
        assert len(results) == 1
        assert results[0]["video_id"] == "vid_bad"

    def test_global_summary(self, tracker):
        """Global summary should aggregate across all videos."""
        tracker.record_impression("a")
        tracker.record_impression("b")
        tracker.record_click("a")
        summary = tracker.get_global_summary()
        assert summary["total_videos"] == 2
        assert summary["total_impressions"] == 2
        assert summary["total_clicks"] == 1

    def test_negative_watch_time_ignored(self, tracker):
        """Negative watch time should be silently ignored."""
        tracker.record_click("vid1")
        tracker.record_watch_time("vid1", -5.0)
        stats = tracker.get_stats("vid1")
        assert stats["watch_time_sum"] == 0.0

    def test_nonexistent_video_stats(self, tracker):
        """Querying stats for unknown video should return None."""
        assert tracker.get_stats("nonexistent") is None


# ---------------------------------------------------------------------------
# ab_test
# ---------------------------------------------------------------------------

class TestABTest:
    """Test thumbnail A/B testing."""

    def test_add_variant(self, ab_manager):
        """Adding a variant should be retrievable."""
        ab_manager.add_variant("vid1", "frame_0s", "vid1_0s.jpg", source="auto")
        variants = ab_manager.get_variants("vid1")
        assert len(variants) == 1
        assert variants[0]["variant_key"] == "frame_0s"

    def test_duplicate_variant_ignored(self, ab_manager):
        """Adding the same variant twice should not duplicate."""
        ab_manager.add_variant("vid1", "frame_0s", "vid1_0s.jpg")
        ab_manager.add_variant("vid1", "frame_0s", "vid1_0s_v2.jpg")
        variants = ab_manager.get_variants("vid1")
        assert len(variants) == 1

    def test_pick_variant_random(self, ab_manager):
        """pick_variant should return one of the registered variants."""
        ab_manager.add_variant("vid1", "a", "a.jpg")
        ab_manager.add_variant("vid1", "b", "b.jpg")
        picks = {ab_manager.pick_variant("vid1") for _ in range(50)}
        # With 50 picks, both should appear (probabilistically near-certain)
        assert "a" in picks or "b" in picks

    def test_pick_variant_no_variants(self, ab_manager):
        """pick_variant returns None when no variants exist."""
        assert ab_manager.pick_variant("vid_none") is None

    def test_record_events_and_stats(self, ab_manager):
        """Event recording should be reflected in variant stats."""
        ab_manager.add_variant("vid1", "a", "a.jpg")
        ab_manager.add_variant("vid1", "b", "b.jpg")
        for _ in range(10):
            ab_manager.record_event("vid1", "a", "impression")
        for _ in range(3):
            ab_manager.record_event("vid1", "a", "click")
        stats = ab_manager.get_variant_stats("vid1")
        a_stats = next(s for s in stats if s["variant_key"] == "a")
        assert a_stats["impressions"] == 10
        assert a_stats["clicks"] == 3
        assert abs(a_stats["ctr"] - 0.3) < 0.001

    def test_winner_not_declared_early(self, ab_manager):
        """Winner should not be declared before minimum impressions."""
        ab_manager.add_variant("vid1", "a", "a.jpg")
        ab_manager.add_variant("vid1", "b", "b.jpg")
        for _ in range(50):  # Less than MIN_IMPRESSIONS_PER_VARIANT
            ab_manager.record_event("vid1", "a", "impression")
            ab_manager.record_event("vid1", "b", "impression")
        for _ in range(25):
            ab_manager.record_event("vid1", "a", "click")
        assert ab_manager.check_winner("vid1") is None

    def test_winner_declared_with_clear_lead(self, ab_manager):
        """Winner should be declared when one variant clearly leads."""
        ab_manager.add_variant("vid1", "good", "good.jpg")
        ab_manager.add_variant("vid1", "bad", "bad.jpg")
        n = MIN_IMPRESSIONS_PER_VARIANT
        for _ in range(n):
            ab_manager.record_event("vid1", "good", "impression")
            ab_manager.record_event("vid1", "bad", "impression")
        # good: 40% CTR, bad: 10% CTR
        for _ in range(int(n * 0.4)):
            ab_manager.record_event("vid1", "good", "click")
        for _ in range(int(n * 0.1)):
            ab_manager.record_event("vid1", "bad", "click")

        winner = ab_manager.check_winner("vid1")
        assert winner == "good"
        assert ab_manager.is_locked("vid1")

    def test_locked_winner_always_served(self, ab_manager):
        """Once locked, pick_variant should always return the winner."""
        ab_manager.add_variant("vid1", "good", "good.jpg")
        ab_manager.add_variant("vid1", "bad", "bad.jpg")
        n = MIN_IMPRESSIONS_PER_VARIANT
        for _ in range(n):
            ab_manager.record_event("vid1", "good", "impression")
            ab_manager.record_event("vid1", "bad", "impression")
        for _ in range(int(n * 0.5)):
            ab_manager.record_event("vid1", "good", "click")
        for _ in range(int(n * 0.05)):
            ab_manager.record_event("vid1", "bad", "click")
        ab_manager.check_winner("vid1")

        # 20 picks should all be "good"
        picks = [ab_manager.pick_variant("vid1") for _ in range(20)]
        assert all(p == "good" for p in picks)


# ---------------------------------------------------------------------------
# ranking_signal
# ---------------------------------------------------------------------------

class TestRankingSignal:
    """Test feed ranking score computation."""

    def test_recency_fresh(self):
        """Fresh video should have recency near 1.0."""
        now = time.time()
        assert _recency_score(now, now) == 1.0

    def test_recency_old(self):
        """Old video should have low recency."""
        now = time.time()
        old = now - 7 * 24 * 3600
        assert _recency_score(old, now) < 0.01

    def test_phase_weights_early(self):
        """Early phase should boost CTR weight."""
        w = _phase_weights(1.0)
        w_late = _phase_weights(48.0)
        assert w["ctr"] > w_late["ctr"]

    def test_phase_weights_late_boosts_watch_time(self):
        """Late phase should boost watch_time weight."""
        w_early = _phase_weights(0.0)
        w_late = _phase_weights(48.0)
        assert w_late["watch_time"] > w_early["watch_time"]

    def test_engagement_score_zero(self):
        """Zero engagement should produce zero score."""
        assert _engagement_score(0, 0) == 0.0

    def test_engagement_score_positive(self):
        """Positive engagement should produce positive score."""
        assert _engagement_score(10, 5) > 0

    def test_compute_feed_score_with_data(self, tmp_db):
        """compute_feed_score should work with pre-provided data."""
        # Create the CTR table
        tracker = CTRTracker(tmp_db)
        tracker.init_db()

        now = time.time()
        video_data = {"created_at": now, "likes": 5, "views": 100}
        ctr_data = {"ctr": 0.15, "avg_watch_time": 30.0, "impressions": 200, "clicks": 30}

        score = compute_feed_score(
            "vid1", db_path=tmp_db, now=now,
            video_data=video_data, ctr_data=ctr_data,
        )
        assert score > 0

    def test_compute_feed_score_no_ctr(self, tmp_db):
        """Video with no CTR data should still get a score (from recency/engagement)."""
        tracker = CTRTracker(tmp_db)
        tracker.init_db()
        # Create a minimal videos table
        conn = sqlite3.connect(tmp_db)
        conn.execute("""CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY, created_at REAL, likes INTEGER DEFAULT 0,
            dislikes INTEGER DEFAULT 0, views INTEGER DEFAULT 0
        )""")
        now = time.time()
        conn.execute("INSERT INTO videos VALUES (?, ?, 0, 0, 0)", ("vid1", now))
        conn.commit()
        conn.close()

        score = compute_feed_score("vid1", db_path=tmp_db, now=now)
        assert score > 0  # recency alone should give some score

    def test_integrate_with_feed_sorting(self, tmp_db):
        """integrate_with_feed should sort videos by score descending."""
        tracker = CTRTracker(tmp_db)
        tracker.init_db()

        now = time.time()
        videos = [
            {"video_id": "old", "created_at": now - 7 * 86400, "likes": 0, "views": 0},
            {"video_id": "new", "created_at": now, "likes": 10, "views": 100},
        ]
        sorted_vids = integrate_with_feed(videos, db_path=tmp_db, now=now)
        assert sorted_vids[0]["video_id"] == "new"
        assert "_feed_score" in sorted_vids[0]

    def test_integrate_empty_list(self, tmp_db):
        """integrate_with_feed should handle empty list gracefully."""
        tracker = CTRTracker(tmp_db)
        tracker.init_db()
        result = integrate_with_feed([], db_path=tmp_db)
        assert result == []
