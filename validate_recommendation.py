#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Validation Script for Recommendation Engine (Issue #46)

Runs comprehensive validation tests and generates a report.
"""

import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recommendation_engine import (
    RecommendationEngine,
    fallback_latest,
    get_feed_recommendations,
    score_engagement,
    score_freshness,
)


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------

class ValidationResult:
    """Holds validation test results."""
    
    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.errors = []
        self.warnings = []
        self.metrics = {}
    
    def add_error(self, msg: str):
        self.passed = False
        self.errors.append(msg)
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)
    
    def add_metric(self, key: str, value):
        self.metrics[key] = value
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


def validate_freshness_scoring() -> ValidationResult:
    """Validate freshness scoring behavior."""
    result = ValidationResult("Freshness Scoring")
    
    now = time.time()
    
    # Test 1: Fresh video
    fresh_score = score_freshness(now, now)
    if abs(fresh_score - 1.0) > 0.001:
        result.add_error(f"Fresh video score should be 1.0, got {fresh_score}")
    result.add_metric("fresh_video_score", fresh_score)
    
    # Test 2: 24h old video (half-life)
    old_24h = now - 24 * 3600
    score_24h = score_freshness(old_24h, now)
    if not (0.45 < score_24h < 0.55):
        result.add_error(f"24h video score should be ~0.5, got {score_24h}")
    result.add_metric("24h_video_score", score_24h)
    
    # Test 3: 7 day old video
    old_7d = now - 7 * 24 * 3600
    score_7d = score_freshness(old_7d, now)
    if score_7d >= 0.1:
        result.add_warning(f"7d video score should be <0.1, got {score_7d}")
    result.add_metric("7d_video_score", score_7d)
    
    # Test 4: Monotonic decay
    t1 = now - 3600
    t2 = now - 7200
    if score_freshness(t1, now) <= score_freshness(t2, now):
        result.add_error("Freshness should decay monotonically")
    
    return result


def validate_engagement_scoring() -> ValidationResult:
    """Validate engagement scoring behavior."""
    result = ValidationResult("Engagement Scoring")
    
    # Test 1: Zero engagement
    zero_score = score_engagement(0, 0, 0)
    if zero_score != 0:
        result.add_error(f"Zero engagement should score 0, got {zero_score}")
    
    # Test 2: Views contribution
    views_score = score_engagement(100, 0, 0)
    if views_score != 100:
        result.add_error(f"100 views should score 100, got {views_score}")
    result.add_metric("100_views_score", views_score)
    
    # Test 3: Likes weighted higher
    likes_score = score_engagement(0, 100, 0)
    if likes_score <= views_score:
        result.add_error(f"100 likes ({likes_score}) should exceed 100 views ({views_score})")
    result.add_metric("100_likes_score", likes_score)
    
    # Test 4: Comments weighted highest
    comments_score = score_engagement(0, 0, 100)
    if comments_score <= likes_score:
        result.add_error(f"100 comments ({comments_score}) should exceed 100 likes ({likes_score})")
    result.add_metric("100_comments_score", comments_score)
    
    # Test 5: Recent bonus
    base = score_engagement(100, 10, 5)
    with_recent = score_engagement(100, 10, 5, recent_views=50, recent_comments=10)
    if with_recent <= base:
        result.add_error(f"Recent activity should add bonus")
    result.add_metric("recent_bonus", with_recent - base)
    
    return result


def validate_diversity_penalty() -> ValidationResult:
    """Validate diversity penalty behavior."""
    result = ValidationResult("Diversity Penalty")
    
    from recommendation_engine import compute_diversity_penalty
    
    # Test 1: No penalty for first videos
    penalty = compute_diversity_penalty([], candidate_agent_id=1, candidate_category="music")
    if penalty != 1.0:
        result.add_error(f"First video should have no penalty, got {penalty}")
    
    # Test 2: Penalty after threshold (same agent)
    selected = [{"agent_id": 1, "category": "music"} for _ in range(4)]
    penalty = compute_diversity_penalty(selected, candidate_agent_id=1, candidate_category="music")
    if penalty >= 1.0:
        result.add_error(f"Over-threshold should have penalty <1.0, got {penalty}")
    result.add_metric("over_threshold_penalty", penalty)
    
    # Test 3: Different agents but same category still gets category penalty
    # (category penalty is independent of agent penalty)
    selected = [{"agent_id": i, "category": "music"} for i in range(1, 5)]
    penalty = compute_diversity_penalty(selected, candidate_agent_id=99, candidate_category="music")
    # Category penalty applies (4 music videos already), but no agent penalty
    # This is expected behavior - category diversity is separate from agent diversity
    if penalty >= 1.0:
        result.add_error(f"Category over-threshold should have penalty <1.0, got {penalty}")
    result.add_metric("category_penalty_different_agent", penalty)
    
    # Test 4: Different agents AND different category = no penalty
    selected = [{"agent_id": i, "category": "music"} for i in range(1, 5)]
    penalty = compute_diversity_penalty(selected, candidate_agent_id=99, candidate_category="comedy")
    if penalty != 1.0:
        result.add_error(f"Different agent and category should have no penalty, got {penalty}")
    
    return result


def validate_category_affinity() -> ValidationResult:
    """Validate category affinity behavior."""
    result = ValidationResult("Category Affinity")
    
    from recommendation_engine import compute_category_affinity
    
    now = time.time()
    
    # Test 1: Insufficient history
    history = [{"category": "music", "watched_at": now}]
    affinity = compute_category_affinity(history, "music")
    if affinity != 0.5:
        result.add_error(f"Insufficient history should give 0.5, got {affinity}")
    
    # Test 2: Strong affinity
    history = [{"category": "music", "watched_at": now} for _ in range(10)]
    affinity = compute_category_affinity(history, "music")
    if affinity < 0.8:
        result.add_error(f"Strong history should give >0.8 affinity, got {affinity}")
    result.add_metric("strong_affinity", affinity)
    
    # Test 3: Time decay
    history = [
        {"category": "music", "watched_at": now - 7 * 24 * 3600},
        {"category": "music", "watched_at": now - 7 * 24 * 3600},
        {"category": "comedy", "watched_at": now},
    ]
    music_aff = compute_category_affinity(history, "music")
    comedy_aff = compute_category_affinity(history, "comedy")
    if comedy_aff <= music_aff:
        result.add_error(f"Recent watch should have higher affinity")
    result.add_metric("recent_affinity_advantage", comedy_aff - music_aff)
    
    return result


def validate_recommendation_engine() -> ValidationResult:
    """Validate full recommendation engine."""
    result = ValidationResult("Recommendation Engine")
    
    engine = RecommendationEngine()
    now = time.time()
    
    # Create test videos
    videos = [
        {"video_id": f"v{i}", "agent_id": i % 3 + 1, "category": ["music", "education", "comedy"][i % 3],
         "created_at": now - (i * 3600), "views": i * 100, "likes": i * 10, "comment_count": i * 2}
        for i in range(10)
    ]
    
    # Test 1: Returns correct count
    recs = engine.recommend(videos, limit=5)
    if len(recs) != 5:
        result.add_error(f"Should return 5 recommendations, got {len(recs)}")
    
    # Test 2: All have scores
    for v in recs:
        if "recommend_score" not in v:
            result.add_error(f"Video {v.get('video_id')} missing recommend_score")
    
    # Test 3: Diversity in results
    agent_ids = set(v["agent_id"] for v in recs)
    if len(agent_ids) < 2:
        result.add_warning(f"Low diversity: only {len(agent_ids)} unique agents in recommendations")
    result.add_metric("unique_agents", len(agent_ids))
    
    # Test 4: Deterministic results
    recs2 = engine.recommend(videos, limit=5)
    if [v["video_id"] for v in recs] != [v["video_id"] for v in recs2]:
        result.add_error("Recommendations should be deterministic")
    
    return result


def validate_fallback_latest() -> ValidationResult:
    """Validate deterministic fallback mode."""
    result = ValidationResult("Fallback Latest Mode")
    
    now = time.time()
    videos = [
        {"video_id": "c", "created_at": now - 1000},
        {"video_id": "a", "created_at": now},
        {"video_id": "b", "created_at": now - 500},
    ]
    
    # Test 1: Correct ordering
    recs = fallback_latest(videos, limit=10)
    expected = ["a", "b", "c"]
    actual = [v["video_id"] for v in recs]
    if actual != expected:
        result.add_error(f"Expected order {expected}, got {actual}")
    
    # Test 2: Deterministic
    recs2 = fallback_latest(videos, limit=10)
    if [v["video_id"] for v in recs] != [v["video_id"] for v in recs2]:
        result.add_error("Fallback should be deterministic")
    
    # Test 3: Respects limit
    recs3 = fallback_latest(videos, limit=2)
    if len(recs3) != 2:
        result.add_error(f"Limit should be respected, got {len(recs3)}")
    
    return result


def validate_database_integration() -> ValidationResult:
    """Validate database integration."""
    result = ValidationResult("Database Integration")
    
    import tempfile
    
    # Create temp database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    try:
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        
        # Create minimal schema
        db.executescript("""
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY,
                agent_name TEXT,
                display_name TEXT,
                avatar_url TEXT,
                api_key TEXT,
                is_banned INTEGER DEFAULT 0,
                is_human INTEGER DEFAULT 0
            );
            CREATE TABLE videos (
                id INTEGER PRIMARY KEY,
                video_id TEXT,
                agent_id INTEGER,
                title TEXT,
                description TEXT,
                category TEXT,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                is_removed INTEGER DEFAULT 0,
                created_at REAL
            );
            CREATE TABLE views (
                id INTEGER PRIMARY KEY,
                video_id TEXT,
                agent_id INTEGER,
                created_at REAL
            );
            CREATE TABLE comments (
                id INTEGER PRIMARY KEY,
                video_id TEXT,
                agent_id INTEGER,
                created_at REAL
            );
            CREATE TABLE subscriptions (
                follower_id INTEGER,
                following_id INTEGER,
                created_at REAL,
                PRIMARY KEY (follower_id, following_id)
            );
        """)
        
        now = time.time()
        
        # Insert test data
        db.execute("INSERT INTO agents (agent_name, api_key) VALUES (?, ?)", ("test", "key1"))
        for i in range(5):
            db.execute(
                "INSERT INTO videos (video_id, agent_id, title, category, views, likes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"v{i}", 1, f"Video {i}", "music", i * 100, i * 10, now - i * 3600)
            )
        db.commit()
        
        # Test latest mode
        videos, mode = get_feed_recommendations(db, limit=5, mode="latest")
        if mode != "latest":
            result.add_error(f"Expected mode 'latest', got '{mode}'")
        if len(videos) != 5:
            result.add_error(f"Expected 5 videos, got {len(videos)}")
        
        # Test category filter
        videos, _ = get_feed_recommendations(db, limit=10, category="music")
        if len(videos) != 5:
            result.add_error(f"Category filter failed, got {len(videos)} videos")
        
        # Test excluded agent
        videos, _ = get_feed_recommendations(db, exclude_agent=1, limit=10)
        if len(videos) != 0:
            result.add_error(f"Exclude agent failed, got {len(videos)} videos")
        
        result.add_metric("db_videos_returned", len(videos))
        
        db.close()
        
    finally:
        os.unlink(db_path)
    
    return result


def validate_performance() -> ValidationResult:
    """Validate recommendation performance."""
    result = ValidationResult("Performance")
    
    engine = RecommendationEngine()
    now = time.time()
    
    # Create 100 test videos
    videos = [
        {"video_id": f"v{i}", "agent_id": i % 10 + 1, "category": f"cat{i % 5}",
         "created_at": now - (i * 3600), "views": i * 100, "likes": i * 10, "comment_count": i}
        for i in range(100)
    ]
    
    # Time recommendation
    start = time.time()
    recs = engine.recommend(videos, limit=20)
    elapsed = time.time() - start
    
    if elapsed > 1.0:
        result.add_warning(f"Recommendation took {elapsed:.3f}s (should be <1s)")
    result.add_metric("recommendation_time_ms", elapsed * 1000)
    result.add_metric("videos_processed", len(videos))
    result.add_metric("recommendations_returned", len(recs))
    
    return result


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def generate_report(results: list) -> str:
    """Generate validation report."""
    lines = []
    lines.append("=" * 60)
    lines.append("RECOMMENDATION ENGINE VALIDATION REPORT (Issue #46)")
    lines.append("=" * 60)
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append("")
    
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    
    lines.append(f"SUMMARY: {passed}/{total} tests passed")
    lines.append("")
    
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        lines.append("-" * 40)
        lines.append(f"[{status}] {result.name}")
        
        if result.metrics:
            lines.append("  Metrics:")
            for key, value in result.metrics.items():
                if isinstance(value, float):
                    lines.append(f"    - {key}: {value:.4f}")
                else:
                    lines.append(f"    - {key}: {value}")
        
        if result.warnings:
            lines.append("  Warnings:")
            for w in result.warnings:
                lines.append(f"    - {w}")
        
        if result.errors:
            lines.append("  Errors:")
            for e in result.errors:
                lines.append(f"    - {e}")
    
    lines.append("")
    lines.append("=" * 60)
    
    if passed == total:
        lines.append("VALIDATION PASSED - All tests successful")
    else:
        lines.append(f"VALIDATION FAILED - {total - passed} test(s) failed")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


def main():
    """Run all validations and generate report."""
    print("Running recommendation engine validation...")
    print("")
    
    results = [
        validate_freshness_scoring(),
        validate_engagement_scoring(),
        validate_diversity_penalty(),
        validate_category_affinity(),
        validate_recommendation_engine(),
        validate_fallback_latest(),
        validate_database_integration(),
        validate_performance(),
    ]
    
    report = generate_report(results)
    print(report)
    
    # Save report to file
    report_path = ROOT / "validation_report.txt"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")
    
    # Also save JSON results
    json_path = ROOT / "validation_results.json"
    with open(json_path, "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)
    print(f"JSON results saved to: {json_path}")
    
    # Exit with error if any tests failed
    passed = sum(1 for r in results if r.passed)
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
