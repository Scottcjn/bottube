# SPDX-License-Identifier: MIT
"""
CTR (Click-Through Rate) Tracker for BoTTube

Tracks impressions (video shown in feed), clicks (video opened/watched),
and watch time for each video.  All data stored in SQLite alongside the
main BoTTube database.

Usage:
    tracker = CTRTracker(db_path)
    tracker.init_db()

    tracker.record_impression("abc123")
    tracker.record_click("abc123")
    tracker.record_watch_time("abc123", 12.5)

    top = tracker.get_top_by_ctr(limit=10)
    underperformers = tracker.get_underperforming(min_impressions=50, max_ctr=0.02)
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class CTRTracker:
    """Click-through rate and watch time tracker backed by SQLite."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def init_db(self) -> None:
        """Create tables if they do not exist."""
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS video_ctr (
                video_id TEXT PRIMARY KEY,
                impressions INTEGER NOT NULL DEFAULT 0,
                clicks INTEGER NOT NULL DEFAULT 0,
                watch_time_sum REAL NOT NULL DEFAULT 0.0,
                ctr REAL NOT NULL DEFAULT 0.0,
                avg_watch_time REAL NOT NULL DEFAULT 0.0,
                last_updated REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_video_ctr_ctr
                ON video_ctr(ctr DESC);
            CREATE INDEX IF NOT EXISTS idx_video_ctr_impressions
                ON video_ctr(impressions DESC);
        """)
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Recording events
    # ------------------------------------------------------------------

    def _ensure_row(self, conn: sqlite3.Connection, video_id: str) -> None:
        """Insert a default row if the video has no CTR record yet."""
        conn.execute(
            "INSERT OR IGNORE INTO video_ctr (video_id, last_updated) VALUES (?, ?)",
            (video_id, time.time()),
        )

    def _recompute(self, conn: sqlite3.Connection, video_id: str) -> None:
        """Recompute derived fields (ctr, avg_watch_time) after a change."""
        conn.execute(
            """UPDATE video_ctr SET
                ctr = CASE WHEN impressions > 0
                      THEN CAST(clicks AS REAL) / impressions
                      ELSE 0.0 END,
                avg_watch_time = CASE WHEN clicks > 0
                      THEN watch_time_sum / clicks
                      ELSE 0.0 END,
                last_updated = ?
            WHERE video_id = ?""",
            (time.time(), video_id),
        )

    def record_impression(self, video_id: str) -> None:
        """Record that a video was shown in a feed or listing."""
        conn = self._connect()
        try:
            self._ensure_row(conn, video_id)
            conn.execute(
                "UPDATE video_ctr SET impressions = impressions + 1 WHERE video_id = ?",
                (video_id,),
            )
            self._recompute(conn, video_id)
            conn.commit()
        finally:
            conn.close()

    def record_impressions_batch(self, video_ids: List[str]) -> None:
        """Record impressions for multiple videos in a single transaction."""
        if not video_ids:
            return
        conn = self._connect()
        try:
            now = time.time()
            for vid in video_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO video_ctr (video_id, last_updated) VALUES (?, ?)",
                    (vid, now),
                )
                conn.execute(
                    "UPDATE video_ctr SET impressions = impressions + 1 WHERE video_id = ?",
                    (vid,),
                )
            # Batch recompute
            for vid in set(video_ids):
                self._recompute(conn, vid)
            conn.commit()
        finally:
            conn.close()

    def record_click(self, video_id: str) -> None:
        """Record that a video was clicked/opened."""
        conn = self._connect()
        try:
            self._ensure_row(conn, video_id)
            conn.execute(
                "UPDATE video_ctr SET clicks = clicks + 1 WHERE video_id = ?",
                (video_id,),
            )
            self._recompute(conn, video_id)
            conn.commit()
        finally:
            conn.close()

    def record_watch_time(self, video_id: str, seconds: float) -> None:
        """Record watch time for a video (accumulated per view)."""
        if seconds <= 0:
            return
        conn = self._connect()
        try:
            self._ensure_row(conn, video_id)
            conn.execute(
                "UPDATE video_ctr SET watch_time_sum = watch_time_sum + ? WHERE video_id = ?",
                (seconds, video_id),
            )
            self._recompute(conn, video_id)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_stats(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get CTR stats for a single video."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM video_ctr WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_top_by_ctr(
        self, limit: int = 20, min_impressions: int = 10
    ) -> List[Dict[str, Any]]:
        """Get videos ranked by CTR, filtered by minimum impressions.

        Requiring min_impressions avoids ranking flukes where 1/1 = 100% CTR.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM video_ctr
                   WHERE impressions >= ?
                   ORDER BY ctr DESC
                   LIMIT ?""",
                (min_impressions, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_top_by_watch_time(
        self, limit: int = 20, min_clicks: int = 5
    ) -> List[Dict[str, Any]]:
        """Get videos ranked by average watch time."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM video_ctr
                   WHERE clicks >= ?
                   ORDER BY avg_watch_time DESC
                   LIMIT ?""",
                (min_clicks, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_underperforming(
        self, min_impressions: int = 50, max_ctr: float = 0.02
    ) -> List[Dict[str, Any]]:
        """Get videos that have many impressions but low CTR.

        Candidates for thumbnail refresh or A/B testing.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM video_ctr
                   WHERE impressions >= ? AND ctr <= ?
                   ORDER BY impressions DESC
                   LIMIT 50""",
                (min_impressions, max_ctr),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_all_stats(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get CTR stats for all tracked videos, ordered by last_updated."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM video_ctr ORDER BY last_updated DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_global_summary(self) -> Dict[str, Any]:
        """Get aggregate CTR statistics across all videos."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT
                    COUNT(*) as total_videos,
                    SUM(impressions) as total_impressions,
                    SUM(clicks) as total_clicks,
                    SUM(watch_time_sum) as total_watch_time,
                    CASE WHEN SUM(impressions) > 0
                         THEN CAST(SUM(clicks) AS REAL) / SUM(impressions)
                         ELSE 0.0 END as global_ctr,
                    AVG(ctr) as avg_video_ctr
                FROM video_ctr"""
            ).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()
