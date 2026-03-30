# SPDX-License-Identifier: MIT
"""
Thumbnail A/B Testing for BoTTube

Stores multiple thumbnail variants per video, randomly serves them on feed
views, tracks per-variant CTR, and auto-locks the winner after sufficient
impressions.

Usage:
    manager = ABTestManager(db_path)
    manager.init_db()

    manager.add_variant("vid123", "frame_0s", "vid123_0s.jpg", source="auto")
    manager.add_variant("vid123", "frame_2s", "vid123_2s.jpg", source="auto")

    variant = manager.pick_variant("vid123")  # random serving
    manager.record_event("vid123", variant, "impression")
    manager.record_event("vid123", variant, "click")

    winner = manager.check_winner("vid123")  # auto-lock if threshold met
"""

from __future__ import annotations

import random
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Minimum impressions per variant before a winner can be declared
MIN_IMPRESSIONS_PER_VARIANT = 100

# Minimum CTR lift (relative) for a winner to be declared
MIN_CTR_LIFT = 0.10  # 10% relative improvement


class ABTestManager:
    """Thumbnail A/B test manager backed by SQLite."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def init_db(self) -> None:
        """Create A/B testing tables if they do not exist."""
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS thumbnail_variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                variant_key TEXT NOT NULL,
                filename TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'auto',
                created_at REAL NOT NULL,
                UNIQUE(video_id, variant_key)
            );
            CREATE INDEX IF NOT EXISTS idx_thumb_variants_video
                ON thumbnail_variants(video_id);

            CREATE TABLE IF NOT EXISTS variant_impressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                variant_key TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'impression',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_variant_imp_video
                ON variant_impressions(video_id, variant_key);

            CREATE TABLE IF NOT EXISTS ab_test_results (
                video_id TEXT PRIMARY KEY,
                winning_variant TEXT NOT NULL,
                winning_ctr REAL NOT NULL DEFAULT 0.0,
                total_impressions INTEGER NOT NULL DEFAULT 0,
                locked_at REAL NOT NULL
            );
        """)
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Variant management
    # ------------------------------------------------------------------

    def add_variant(
        self,
        video_id: str,
        variant_key: str,
        filename: str,
        source: str = "auto",
    ) -> bool:
        """Register a thumbnail variant for a video.

        Args:
            video_id: The video this variant belongs to.
            variant_key: Unique key within the video (e.g. "frame_0s", "ai_gen").
            filename: Thumbnail filename on disk.
            source: How the variant was created ('auto', 'upload', 'ai_gen').

        Returns:
            True if inserted, False if already exists.
        """
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO thumbnail_variants
                   (video_id, variant_key, filename, source, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (video_id, variant_key, filename, source, time.time()),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    def get_variants(self, video_id: str) -> List[Dict[str, Any]]:
        """Get all thumbnail variants for a video."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM thumbnail_variants WHERE video_id = ? ORDER BY created_at",
                (video_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def remove_variant(self, video_id: str, variant_key: str) -> bool:
        """Remove a thumbnail variant."""
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM thumbnail_variants WHERE video_id = ? AND variant_key = ?",
                (video_id, variant_key),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Serving
    # ------------------------------------------------------------------

    def pick_variant(self, video_id: str) -> Optional[str]:
        """Pick a random variant to serve for a video.

        If a winner is already locked, always returns the winner.
        If no variants exist, returns None.

        Returns:
            variant_key string or None.
        """
        conn = self._connect()
        try:
            # Check for locked winner first
            winner = conn.execute(
                "SELECT winning_variant FROM ab_test_results WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            if winner:
                return winner["winning_variant"]

            # Get all variants
            rows = conn.execute(
                "SELECT variant_key FROM thumbnail_variants WHERE video_id = ?",
                (video_id,),
            ).fetchall()
            if not rows:
                return None

            return random.choice(rows)["variant_key"]
        finally:
            conn.close()

    def get_variant_filename(self, video_id: str, variant_key: str) -> Optional[str]:
        """Get the filename for a specific variant."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT filename FROM thumbnail_variants WHERE video_id = ? AND variant_key = ?",
                (video_id, variant_key),
            ).fetchone()
            return row["filename"] if row else None
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------

    def record_event(
        self, video_id: str, variant_key: str, event_type: str = "impression"
    ) -> None:
        """Record an impression or click for a specific variant.

        Args:
            video_id: Video ID.
            variant_key: Which variant was shown/clicked.
            event_type: 'impression' or 'click'.
        """
        if event_type not in ("impression", "click"):
            return
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO variant_impressions
                   (video_id, variant_key, event_type, created_at)
                   VALUES (?, ?, ?, ?)""",
                (video_id, variant_key, event_type, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_variant_stats(self, video_id: str) -> List[Dict[str, Any]]:
        """Get per-variant impression and click counts plus CTR.

        Returns list of dicts with variant_key, impressions, clicks, ctr.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT
                    tv.variant_key,
                    tv.filename,
                    tv.source,
                    COALESCE(imp.cnt, 0) as impressions,
                    COALESCE(clk.cnt, 0) as clicks,
                    CASE WHEN COALESCE(imp.cnt, 0) > 0
                         THEN CAST(COALESCE(clk.cnt, 0) AS REAL) / imp.cnt
                         ELSE 0.0 END as ctr
                FROM thumbnail_variants tv
                LEFT JOIN (
                    SELECT variant_key, COUNT(*) as cnt
                    FROM variant_impressions
                    WHERE video_id = ? AND event_type = 'impression'
                    GROUP BY variant_key
                ) imp ON imp.variant_key = tv.variant_key
                LEFT JOIN (
                    SELECT variant_key, COUNT(*) as cnt
                    FROM variant_impressions
                    WHERE video_id = ? AND event_type = 'click'
                    GROUP BY variant_key
                ) clk ON clk.variant_key = tv.variant_key
                WHERE tv.video_id = ?
                ORDER BY ctr DESC""",
                (video_id, video_id, video_id),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Winner selection
    # ------------------------------------------------------------------

    def check_winner(self, video_id: str) -> Optional[str]:
        """Check if a variant has won the A/B test and lock if so.

        A winner is declared when:
        1. All variants have >= MIN_IMPRESSIONS_PER_VARIANT impressions
        2. The best variant has >= MIN_CTR_LIFT relative improvement over second

        Returns the winning variant_key or None if test is still running.
        """
        conn = self._connect()
        try:
            # Already locked?
            existing = conn.execute(
                "SELECT winning_variant FROM ab_test_results WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            if existing:
                return existing["winning_variant"]

            stats = self.get_variant_stats(video_id)
            if len(stats) < 2:
                # Need at least 2 variants for an A/B test
                return stats[0]["variant_key"] if stats else None

            # Check minimum impressions on all variants
            for s in stats:
                if s["impressions"] < MIN_IMPRESSIONS_PER_VARIANT:
                    return None  # Not enough data yet

            # Sort by CTR descending
            stats.sort(key=lambda s: s["ctr"], reverse=True)
            best = stats[0]
            second = stats[1]

            # Check sufficient lift
            if second["ctr"] > 0:
                lift = (best["ctr"] - second["ctr"]) / second["ctr"]
            else:
                lift = 1.0 if best["ctr"] > 0 else 0.0

            if lift >= MIN_CTR_LIFT:
                total_imp = sum(s["impressions"] for s in stats)
                conn.execute(
                    """INSERT OR REPLACE INTO ab_test_results
                       (video_id, winning_variant, winning_ctr, total_impressions, locked_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (video_id, best["variant_key"], best["ctr"], total_imp, time.time()),
                )
                conn.commit()
                return best["variant_key"]

            return None  # No clear winner yet
        finally:
            conn.close()

    def is_locked(self, video_id: str) -> bool:
        """Check if an A/B test has been locked (winner declared)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM ab_test_results WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def get_winner(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get the locked winner for a video, if any."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM ab_test_results WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
