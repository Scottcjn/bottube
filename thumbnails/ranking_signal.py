# SPDX-License-Identifier: MIT
"""
Feed Ranking Integration for BoTTube

Computes video feed scores using CTR, watch time, recency, and engagement
signals.  Designed to plug into the existing recommendation_engine.py flow.

CTR is weighted heavily in the first 24 hours (cold start signal), then
watch_time dominates (retention signal).

Usage:
    from thumbnails.ranking_signal import compute_feed_score, integrate_with_feed

    score = compute_feed_score(video_id, db_path="/path/to/bottube.db")
    sorted_videos = integrate_with_feed(videos, db_path="/path/to/bottube.db")
"""

from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Weight configuration
# ---------------------------------------------------------------------------

# Base weights (sum to ~1.0 for interpretability)
WATCH_TIME_WEIGHT = 0.35
CTR_WEIGHT = 0.30
RECENCY_WEIGHT = 0.20
ENGAGEMENT_WEIGHT = 0.15

# CTR is boosted early (first 24h) and fades; watch_time grows over time
EARLY_HOURS = 24.0  # hours during which CTR gets extra weight
CTR_EARLY_BOOST = 1.8  # multiplier on CTR weight during early phase
WATCH_TIME_LATE_BOOST = 1.5  # multiplier on watch_time after early phase

# Recency half-life (matches recommendation_engine.py FRESHNESS_HALF_LIFE_HOURS)
RECENCY_HALF_LIFE_HOURS = 24.0


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def _recency_score(created_at: float, now: float) -> float:
    """Exponential decay freshness score in (0, 1]."""
    age_hours = max(0, (now - created_at) / 3600.0)
    return math.pow(2, -age_hours / RECENCY_HALF_LIFE_HOURS)


def _engagement_score(likes: int, comments: int) -> float:
    """Log-scaled engagement score from likes + comments."""
    raw = likes * 3.0 + comments * 4.0
    return math.log1p(raw)


def _phase_weights(age_hours: float) -> Dict[str, float]:
    """Compute phase-adjusted weights based on video age.

    Early phase (< 24h): CTR boosted, watch_time normal.
    Late phase (>= 24h): watch_time boosted, CTR fades back to base.
    """
    if age_hours < EARLY_HOURS:
        # Smooth transition using cosine
        t = age_hours / EARLY_HOURS  # 0 to 1
        ctr_mult = CTR_EARLY_BOOST - (CTR_EARLY_BOOST - 1.0) * t
        wt_mult = 1.0 + (WATCH_TIME_LATE_BOOST - 1.0) * t
    else:
        ctr_mult = 1.0
        wt_mult = WATCH_TIME_LATE_BOOST

    return {
        "watch_time": WATCH_TIME_WEIGHT * wt_mult,
        "ctr": CTR_WEIGHT * ctr_mult,
        "recency": RECENCY_WEIGHT,
        "engagement": ENGAGEMENT_WEIGHT,
    }


def compute_feed_score(
    video_id: str,
    db_path: str | Path = "bottube.db",
    now: Optional[float] = None,
    video_data: Optional[Dict[str, Any]] = None,
    ctr_data: Optional[Dict[str, Any]] = None,
) -> float:
    """Compute the composite feed ranking score for a video.

    Args:
        video_id: The video to score.
        db_path: Path to the BoTTube SQLite database.
        now: Current timestamp (defaults to time.time()).
        video_data: Pre-fetched video row dict (avoids DB hit if provided).
        ctr_data: Pre-fetched CTR row dict (avoids DB hit if provided).

    Returns:
        Float score (higher = rank higher in feed).
    """
    if now is None:
        now = time.time()

    db_path = str(db_path)

    # Fetch video metadata if not provided
    if video_data is None:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT created_at, likes, dislikes, views FROM videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        conn.close()
        if not row:
            return 0.0
        video_data = dict(row)

    # Fetch CTR data if not provided
    if ctr_data is None:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT impressions, clicks, ctr, avg_watch_time FROM video_ctr WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        conn.close()
        ctr_data = dict(row) if row else {}

    created_at = video_data.get("created_at", now)
    age_hours = max(0, (now - created_at) / 3600.0)

    # Phase-adjusted weights
    weights = _phase_weights(age_hours)

    # CTR score: raw CTR capped at 1.0
    ctr = min(1.0, ctr_data.get("ctr", 0.0))

    # Watch time: log-scaled average watch time (seconds)
    avg_wt = ctr_data.get("avg_watch_time", 0.0)
    wt_score = math.log1p(avg_wt) / math.log1p(120.0)  # normalize vs 2min ceiling
    wt_score = min(1.0, wt_score)

    # Recency
    recency = _recency_score(created_at, now)

    # Engagement (likes + comment proxy via views as fallback)
    likes = video_data.get("likes", 0)
    # We don't have direct comment count in video_data, use 0 as safe default
    comments = 0
    eng = _engagement_score(likes, comments)
    eng_normalized = min(1.0, eng / 5.0)  # normalize

    score = (
        weights["watch_time"] * wt_score
        + weights["ctr"] * ctr
        + weights["recency"] * recency
        + weights["engagement"] * eng_normalized
    )

    return round(score, 6)


def integrate_with_feed(
    videos: List[Dict[str, Any]],
    db_path: str | Path = "bottube.db",
    now: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Sort a list of video dicts by composite feed score (descending).

    Each video dict should contain at least 'video_id'.  The function fetches
    CTR data in bulk and computes scores, then returns the list sorted with
    a '_feed_score' field added to each dict.

    Args:
        videos: List of video dicts from the existing feed pipeline.
        db_path: Path to the BoTTube database.
        now: Current timestamp.

    Returns:
        The same list, sorted by feed score descending, with _feed_score added.
    """
    if now is None:
        now = time.time()
    if not videos:
        return videos

    db_path = str(db_path)

    # Bulk fetch CTR data
    video_ids = [v.get("video_id") or v.get("id", "") for v in videos]
    ctr_map: Dict[str, Dict[str, Any]] = {}

    if video_ids:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in video_ids)
        rows = conn.execute(
            f"SELECT * FROM video_ctr WHERE video_id IN ({placeholders})",
            video_ids,
        ).fetchall()
        conn.close()
        for r in rows:
            ctr_map[r["video_id"]] = dict(r)

    # Score each video
    for v in videos:
        vid = v.get("video_id") or v.get("id", "")
        v["_feed_score"] = compute_feed_score(
            vid,
            db_path=db_path,
            now=now,
            video_data=v,
            ctr_data=ctr_map.get(vid),
        )

    # Sort descending by score
    videos.sort(key=lambda v: v.get("_feed_score", 0), reverse=True)
    return videos
