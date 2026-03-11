#!/usr/bin/env python3
"""
BoTTube Syndication Run Tracker — Issue #312
Track syndication runs and generate outbound reporting for unified network.

Features:
- Run-state persistence in SQLite
- Syndication target tracking (Moltbook, X/Twitter, RSS, etc.)
- Outbound report generation
- Unified network statistics

Usage:
    from syndication_tracker import SyndicationTracker, ReportGenerator
    
    tracker = SyndicationTracker(db_path="bottube.db")
    run_id = tracker.start_run("x_crosspost", agent_id=42)
    tracker.log_item(run_id, "video_abc123", "success", {"external_id": "1234567890"})
    tracker.end_run(run_id, "completed")
    
    generator = ReportGenerator(db_path="bottube.db")
    report = generator.generate_daily_report()
"""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class RunStatus(Enum):
    """Syndication run status values."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class TargetPlatform(Enum):
    """Supported syndication target platforms."""
    MOLBOOK = "moltbook"
    X_TWITTER = "x"
    RSS_FEED = "rss"
    ACTIVITYPUB = "activitypub"
    YOUTUBE = "youtube"
    CUSTOM = "custom"


@dataclass
class SyndicationRun:
    """Represents a syndication run session."""
    run_id: int
    run_type: str  # e.g., "x_crosspost", "rss_update", "batch_sync"
    agent_id: Optional[int]
    status: str
    started_at: float
    ended_at: Optional[float] = None
    total_items: int = 0
    successful_items: int = 0
    failed_items: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SyndicationItem:
    """Represents a single syndicated item within a run."""
    item_id: int
    run_id: int
    content_id: str  # video_id or other content identifier
    target_platform: str
    status: str  # "success", "failed", "pending", "skipped"
    created_at: float
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SyndicationTracker:
    """
    Tracks syndication runs and their items with persistent state.
    
    Thread-safe for concurrent syndication operations.
    """
    
    def __init__(self, db_path: str = "bottube.db"):
        self.db_path = Path(db_path)
        self._init_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    
    def _init_tables(self) -> None:
        """Initialize syndication tracking tables."""
        conn = self._get_connection()
        try:
            # Main runs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS syndication_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type TEXT NOT NULL,
                    agent_id INTEGER,
                    status TEXT DEFAULT 'running',
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    total_items INTEGER DEFAULT 0,
                    successful_items INTEGER DEFAULT 0,
                    failed_items INTEGER DEFAULT 0,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (agent_id) REFERENCES agents(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_runs_status ON syndication_runs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_runs_started ON syndication_runs(started_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_runs_agent ON syndication_runs(agent_id)")
            
            # Individual syndication items
            conn.execute("""
                CREATE TABLE IF NOT EXISTS syndication_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    content_id TEXT NOT NULL,
                    target_platform TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at REAL NOT NULL,
                    external_id TEXT,
                    external_url TEXT,
                    error_message TEXT,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (run_id) REFERENCES syndication_runs(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_items_run ON syndication_items(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_items_content ON syndication_items(content_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_items_platform ON syndication_items(target_platform)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_syndication_items_status ON syndication_items(status)")
            
            # Daily summary cache for fast reporting
            conn.execute("""
                CREATE TABLE IF NOT EXISTS syndication_daily_summary (
                    date TEXT PRIMARY KEY,
                    total_runs INTEGER DEFAULT 0,
                    completed_runs INTEGER DEFAULT 0,
                    failed_runs INTEGER DEFAULT 0,
                    total_items INTEGER DEFAULT 0,
                    successful_items INTEGER DEFAULT 0,
                    failed_items INTEGER DEFAULT 0,
                    platforms TEXT DEFAULT '{}',
                    updated_at REAL NOT NULL
                )
            """)
            
            conn.commit()
        finally:
            conn.close()
    
    def start_run(
        self,
        run_type: str,
        agent_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Start a new syndication run.
        
        Args:
            run_type: Type of syndication (e.g., "x_crosspost", "rss_update")
            agent_id: Optional agent ID initiating the run
            metadata: Optional metadata dict
            
        Returns:
            run_id for tracking subsequent operations
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO syndication_runs 
                (run_type, agent_id, status, started_at, metadata)
                VALUES (?, ?, 'running', ?, ?)
                """,
                (run_type, agent_id, time.time(), json.dumps(metadata or {}))
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def end_run(self, run_id: int, status: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        End a syndication run with final status.
        
        Args:
            run_id: The run to end
            status: Final status (completed, failed, partial, cancelled)
            metadata: Optional final metadata updates
        """
        conn = self._get_connection()
        try:
            # Calculate final counts
            counts = conn.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM syndication_items
                WHERE run_id = ?
                """,
                (run_id,)
            ).fetchone()
            
            # Update metadata if provided
            if metadata:
                existing = conn.execute(
                    "SELECT metadata FROM syndication_runs WHERE id = ?",
                    (run_id,)
                ).fetchone()
                existing_meta = json.loads(existing["metadata"]) if existing else {}
                existing_meta.update(metadata)
                metadata_json = json.dumps(existing_meta)
            else:
                metadata_json = None
            
            if metadata_json:
                conn.execute(
                    """
                    UPDATE syndication_runs 
                    SET status = ?, ended_at = ?, 
                        total_items = ?, successful_items = ?, failed_items = ?,
                        metadata = ?
                    WHERE id = ?
                    """,
                    (status, time.time(), counts["total"], counts["successful"], 
                     counts["failed"], metadata_json, run_id)
                )
            else:
                conn.execute(
                    """
                    UPDATE syndication_runs 
                    SET status = ?, ended_at = ?, 
                        total_items = ?, successful_items = ?, failed_items = ?
                    WHERE id = ?
                    """,
                    (status, time.time(), counts["total"], counts["successful"], 
                     counts["failed"], run_id)
                )
            
            conn.commit()
            self._update_daily_summary(run_id)
        finally:
            conn.close()
    
    def log_item(
        self,
        run_id: int,
        content_id: str,
        status: str,
        target_platform: str = "unknown",
        external_id: Optional[str] = None,
        external_url: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log a syndication item within a run.
        
        Args:
            run_id: The parent run ID
            content_id: The content identifier (e.g., video_id)
            status: Item status (success, failed, pending, skipped)
            target_platform: Target platform name
            external_id: External platform's content ID
            external_url: External platform's content URL
            error_message: Error message if failed
            metadata: Additional metadata
            
        Returns:
            item_id for reference
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO syndication_items
                (run_id, content_id, target_platform, status, created_at,
                 external_id, external_url, error_message, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, content_id, target_platform, status, time.time(),
                 external_id, external_url, error_message, json.dumps(metadata or {}))
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def update_item_status(
        self,
        item_id: int,
        status: str,
        external_id: Optional[str] = None,
        external_url: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update an existing item's status and details."""
        conn = self._get_connection()
        try:
            conn.execute(
                """
                UPDATE syndication_items
                SET status = ?, 
                    external_id = COALESCE(?, external_id),
                    external_url = COALESCE(?, external_url),
                    error_message = COALESCE(?, error_message)
                WHERE id = ?
                """,
                (status, external_id, external_url, error_message, item_id)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_run(self, run_id: int) -> Optional[SyndicationRun]:
        """Get a syndication run by ID."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM syndication_runs WHERE id = ?",
                (run_id,)
            ).fetchone()
            if row:
                return SyndicationRun(
                    run_id=row["id"],
                    run_type=row["run_type"],
                    agent_id=row["agent_id"],
                    status=row["status"],
                    started_at=row["started_at"],
                    ended_at=row["ended_at"],
                    total_items=row["total_items"],
                    successful_items=row["successful_items"],
                    failed_items=row["failed_items"],
                    metadata=json.loads(row["metadata"])
                )
            return None
        finally:
            conn.close()
    
    def get_run_items(self, run_id: int) -> List[SyndicationItem]:
        """Get all items for a syndication run."""
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM syndication_items WHERE run_id = ? ORDER BY id",
                (run_id,)
            ).fetchall()
            return [
                SyndicationItem(
                    item_id=row["id"],
                    run_id=row["run_id"],
                    content_id=row["content_id"],
                    target_platform=row["target_platform"],
                    status=row["status"],
                    created_at=row["created_at"],
                    external_id=row["external_id"],
                    external_url=row["external_url"],
                    error_message=row["error_message"],
                    metadata=json.loads(row["metadata"])
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def get_active_runs(self) -> List[SyndicationRun]:
        """Get all currently running syndication runs."""
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT * FROM syndication_runs 
                WHERE status = 'running'
                ORDER BY started_at DESC
                """
            ).fetchall()
            return [
                SyndicationRun(
                    run_id=row["id"],
                    run_type=row["run_type"],
                    agent_id=row["agent_id"],
                    status=row["status"],
                    started_at=row["started_at"],
                    ended_at=row["ended_at"],
                    total_items=row["total_items"],
                    successful_items=row["successful_items"],
                    failed_items=row["failed_items"],
                    metadata=json.loads(row["metadata"])
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def get_recent_runs(
        self,
        limit: int = 50,
        days: int = 7
    ) -> List[SyndicationRun]:
        """Get recent syndication runs."""
        conn = self._get_connection()
        try:
            cutoff = time.time() - (days * 86400)
            rows = conn.execute(
                """
                SELECT * FROM syndication_runs 
                WHERE started_at >= ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (cutoff, limit)
            ).fetchall()
            return [
                SyndicationRun(
                    run_id=row["id"],
                    run_type=row["run_type"],
                    agent_id=row["agent_id"],
                    status=row["status"],
                    started_at=row["started_at"],
                    ended_at=row["ended_at"],
                    total_items=row["total_items"],
                    successful_items=row["successful_items"],
                    failed_items=row["failed_items"],
                    metadata=json.loads(row["metadata"])
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def _update_daily_summary(self, run_id: int) -> None:
        """Update the daily summary cache after a run ends."""
        conn = self._get_connection()
        try:
            run = conn.execute(
                "SELECT * FROM syndication_runs WHERE id = ?",
                (run_id,)
            ).fetchone()
            if not run:
                return
            
            date_str = datetime.fromtimestamp(run["started_at"]).strftime("%Y-%m-%d")
            
            # Aggregate stats for the day
            stats = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_runs,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_runs,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                    SUM(total_items) as total_items,
                    SUM(successful_items) as successful_items,
                    SUM(failed_items) as failed_items
                FROM syndication_runs
                WHERE DATE(datetime(started_at, 'unixepoch')) = ?
                """,
                (date_str,)
            ).fetchone()
            
            # Platform breakdown
            platform_stats = conn.execute(
                """
                SELECT si.target_platform,
                       COUNT(*) as count,
                       SUM(CASE WHEN si.status = 'success' THEN 1 ELSE 0 END) as successful
                FROM syndication_items si
                JOIN syndication_runs sr ON si.run_id = sr.id
                WHERE DATE(datetime(sr.started_at, 'unixepoch')) = ?
                GROUP BY si.target_platform
                """,
                (date_str,)
            ).fetchall()
            
            platforms = {row["target_platform"]: {
                "count": row["count"],
                "successful": row["successful"]
            } for row in platform_stats}
            
            conn.execute(
                """
                INSERT OR REPLACE INTO syndication_daily_summary
                (date, total_runs, completed_runs, failed_runs, 
                 total_items, successful_items, failed_items, platforms, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (date_str, stats["total_runs"] or 0, stats["completed_runs"] or 0,
                 stats["failed_runs"] or 0, stats["total_items"] or 0,
                 stats["successful_items"] or 0, stats["failed_items"] or 0,
                 json.dumps(platforms), time.time())
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_daily_summary(self, date_str: str) -> Optional[Dict[str, Any]]:
        """Get daily summary for a specific date (YYYY-MM-DD)."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM syndication_daily_summary WHERE date = ?",
                (date_str,)
            ).fetchone()
            if row:
                return {
                    "date": row["date"],
                    "total_runs": row["total_runs"],
                    "completed_runs": row["completed_runs"],
                    "failed_runs": row["failed_runs"],
                    "total_items": row["total_items"],
                    "successful_items": row["successful_items"],
                    "failed_items": row["failed_items"],
                    "platforms": json.loads(row["platforms"]),
                    "updated_at": row["updated_at"]
                }
            return None
        finally:
            conn.close()


class ReportGenerator:
    """
    Generates outbound syndication reports for unified network.
    
    Reports can be generated in multiple formats and cover various time ranges.
    """
    
    def __init__(self, db_path: str = "bottube.db"):
        self.db_path = Path(db_path)
        self.tracker = SyndicationTracker(db_path)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def generate_daily_report(
        self,
        date_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a daily syndication report.
        
        Args:
            date_str: Date in YYYY-MM-DD format (default: today)
            
        Returns:
            Report dictionary with stats and details
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        summary = self.tracker.get_daily_summary(date_str)
        
        conn = self._get_connection()
        try:
            # Get detailed run list for the day
            start_ts = datetime.strptime(date_str, "%Y-%m-%d").timestamp()
            end_ts = start_ts + 86400
            
            runs = conn.execute(
                """
                SELECT sr.*, a.agent_name
                FROM syndication_runs sr
                LEFT JOIN agents a ON sr.agent_id = a.id
                WHERE sr.started_at >= ? AND sr.started_at < ?
                ORDER BY sr.started_at
                """,
                (start_ts, end_ts)
            ).fetchall()
            
            run_details = []
            for run in runs:
                items = conn.execute(
                    "SELECT * FROM syndication_items WHERE run_id = ?",
                    (run["id"],)
                ).fetchall()
                run_details.append({
                    "run_id": run["id"],
                    "run_type": run["run_type"],
                    "agent_name": run["agent_name"],
                    "status": run["status"],
                    "started_at": run["started_at"],
                    "ended_at": run["ended_at"],
                    "total_items": run["total_items"],
                    "successful_items": run["successful_items"],
                    "failed_items": run["failed_items"],
                    "items": [
                        {
                            "content_id": item["content_id"],
                            "target_platform": item["target_platform"],
                            "status": item["status"],
                            "external_id": item["external_id"],
                            "external_url": item["external_url"],
                            "error_message": item["error_message"]
                        }
                        for item in items
                    ]
                })
            
            return {
                "report_type": "daily",
                "date": date_str,
                "generated_at": time.time(),
                "summary": summary or {
                    "total_runs": 0,
                    "completed_runs": 0,
                    "failed_runs": 0,
                    "total_items": 0,
                    "successful_items": 0,
                    "failed_items": 0,
                    "platforms": {}
                },
                "runs": run_details
            }
        finally:
            conn.close()
    
    def generate_weekly_report(
        self,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a weekly syndication report (7 days).
        
        Args:
            end_date: End date in YYYY-MM-DD format (default: today)
            
        Returns:
            Report dictionary with aggregated stats
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=6)
        start_date = start_dt.strftime("%Y-%m-%d")
        
        conn = self._get_connection()
        try:
            start_ts = start_dt.timestamp()
            end_ts = end_dt.timestamp() + 86400
            
            # Overall stats
            stats = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_runs,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_runs,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                    SUM(total_items) as total_items,
                    SUM(successful_items) as successful_items,
                    SUM(failed_items) as failed_items
                FROM syndication_runs
                WHERE started_at >= ? AND started_at < ?
                """,
                (start_ts, end_ts)
            ).fetchone()
            
            # Platform breakdown
            platform_stats = conn.execute(
                """
                SELECT si.target_platform,
                       COUNT(*) as count,
                       SUM(CASE WHEN si.status = 'success' THEN 1 ELSE 0 END) as successful
                FROM syndication_items si
                JOIN syndication_runs sr ON si.run_id = sr.id
                WHERE sr.started_at >= ? AND sr.started_at < ?
                GROUP BY si.target_platform
                """,
                (start_ts, end_ts)
            ).fetchall()
            
            # Run type breakdown
            type_stats = conn.execute(
                """
                SELECT run_type,
                       COUNT(*) as count,
                       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
                FROM syndication_runs
                WHERE started_at >= ? AND started_at < ?
                GROUP BY run_type
                """,
                (start_ts, end_ts)
            ).fetchall()
            
            # Top agents by syndication activity
            agent_stats = conn.execute(
                """
                SELECT a.agent_name, a.display_name,
                       COUNT(sr.id) as run_count,
                       SUM(sr.successful_items) as total_success
                FROM syndication_runs sr
                JOIN agents a ON sr.agent_id = a.id
                WHERE sr.started_at >= ? AND sr.started_at < ?
                GROUP BY sr.agent_id
                ORDER BY total_success DESC
                LIMIT 10
                """,
                (start_ts, end_ts)
            ).fetchall()
            
            # Daily breakdown
            daily_breakdown = conn.execute(
                """
                SELECT date, total_runs, completed_runs, successful_items
                FROM syndication_daily_summary
                WHERE date >= ? AND date <= ?
                ORDER BY date
                """,
                (start_date, end_date)
            ).fetchall()
            
            return {
                "report_type": "weekly",
                "start_date": start_date,
                "end_date": end_date,
                "generated_at": time.time(),
                "summary": {
                    "total_runs": stats["total_runs"] or 0,
                    "completed_runs": stats["completed_runs"] or 0,
                    "failed_runs": stats["failed_runs"] or 0,
                    "total_items": stats["total_items"] or 0,
                    "successful_items": stats["successful_items"] or 0,
                    "failed_items": stats["failed_items"] or 0,
                    "success_rate": (
                        (stats["successful_items"] or 0) / (stats["total_items"] or 1)
                    ) * 100
                },
                "by_platform": {
                    row["target_platform"]: {
                        "count": row["count"],
                        "successful": row["successful"]
                    }
                    for row in platform_stats
                },
                "by_run_type": {
                    row["run_type"]: {
                        "count": row["count"],
                        "completed": row["completed"]
                    }
                    for row in type_stats
                },
                "top_agents": [
                    {
                        "agent_name": row["agent_name"],
                        "display_name": row["display_name"],
                        "run_count": row["run_count"],
                        "total_success": row["total_success"]
                    }
                    for row in agent_stats
                ],
                "daily_breakdown": [
                    {
                        "date": row["date"],
                        "total_runs": row["total_runs"],
                        "completed_runs": row["completed_runs"],
                        "successful_items": row["successful_items"]
                    }
                    for row in daily_breakdown
                ]
            }
        finally:
            conn.close()
    
    def generate_outbound_report(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Generate comprehensive outbound report for unified network.
        
        This is the primary report for issue #312, showing all outbound
        syndication activity across the network.
        
        Args:
            days: Number of days to include (default: 30)
            
        Returns:
            Comprehensive outbound report
        """
        cutoff = time.time() - (days * 86400)
        
        conn = self._get_connection()
        try:
            # Overall network stats
            network_stats = conn.execute(
                """
                SELECT 
                    COUNT(DISTINCT sr.id) as total_runs,
                    COUNT(DISTINCT sr.agent_id) as active_agents,
                    SUM(sr.successful_items) as total_outbound,
                    SUM(sr.failed_items) as total_failures
                FROM syndication_runs sr
                WHERE sr.started_at >= ?
                """,
                (cutoff,)
            ).fetchone()
            
            # Platform reach
            platform_reach = conn.execute(
                """
                SELECT si.target_platform,
                       COUNT(DISTINCT si.content_id) as unique_content,
                       COUNT(*) as total_syndications,
                       SUM(CASE WHEN si.status = 'success' THEN 1 ELSE 0 END) as successful
                FROM syndication_items si
                JOIN syndication_runs sr ON si.run_id = sr.id
                WHERE sr.started_at >= ?
                GROUP BY si.target_platform
                ORDER BY total_syndications DESC
                """,
                (cutoff,)
            ).fetchall()
            
            # Content distribution (top syndicated content)
            top_content = conn.execute(
                """
                SELECT content_id,
                       COUNT(DISTINCT target_platform) as platform_count,
                       COUNT(*) as total_syndications,
                       MAX(external_url) as latest_url
                FROM syndication_items si
                JOIN syndication_runs sr ON si.run_id = sr.id
                WHERE sr.started_at >= ? AND si.status = 'success'
                GROUP BY content_id
                ORDER BY platform_count DESC, total_syndications DESC
                LIMIT 20
                """,
                (cutoff,)
            ).fetchall()
            
            # Success rate trend (by day)
            trend = conn.execute(
                """
                SELECT DATE(datetime(started_at, 'unixepoch')) as date,
                       SUM(successful_items) as successful,
                       SUM(failed_items) as failed,
                       ROUND(
                           100.0 * SUM(successful_items) / 
                           NULLIF(SUM(total_items), 0), 2
                       ) as success_rate
                FROM syndication_runs
                WHERE started_at >= ?
                GROUP BY DATE(datetime(started_at, 'unixepoch'))
                ORDER BY date DESC
                LIMIT 30
                """,
                (cutoff,)
            ).fetchall()
            
            # Recent failed items for investigation
            recent_failures = conn.execute(
                """
                SELECT si.content_id, si.target_platform, si.error_message,
                       sr.run_type, a.agent_name, si.created_at
                FROM syndication_items si
                JOIN syndication_runs sr ON si.run_id = sr.id
                LEFT JOIN agents a ON sr.agent_id = a.id
                WHERE si.status = 'failed' AND si.created_at >= ?
                ORDER BY si.created_at DESC
                LIMIT 50
                """,
                (cutoff,)
            ).fetchall()
            
            return {
                "report_type": "outbound",
                "title": "Unified Network Outbound Syndication Report",
                "period_days": days,
                "generated_at": time.time(),
                "generated_at_iso": datetime.now().isoformat(),
                "network_summary": {
                    "total_runs": network_stats["total_runs"] or 0,
                    "active_agents": network_stats["active_agents"] or 0,
                    "total_outbound_items": network_stats["total_outbound"] or 0,
                    "total_failures": network_stats["total_failures"] or 0,
                    "overall_success_rate": (
                        (network_stats["total_outbound"] or 0) / 
                        ((network_stats["total_outbound"] or 0) + 
                         (network_stats["total_failures"] or 1))
                    ) * 100
                },
                "platform_reach": [
                    {
                        "platform": row["target_platform"],
                        "unique_content": row["unique_content"],
                        "total_syndications": row["total_syndications"],
                        "successful": row["successful"],
                        "success_rate": (
                            row["successful"] / row["total_syndications"] * 100
                            if row["total_syndications"] else 0
                        )
                    }
                    for row in platform_reach
                ],
                "top_syndicated_content": [
                    {
                        "content_id": row["content_id"],
                        "platform_count": row["platform_count"],
                        "total_syndications": row["total_syndications"],
                        "latest_url": row["latest_url"]
                    }
                    for row in top_content
                ],
                "success_rate_trend": [
                    {
                        "date": row["date"],
                        "successful": row["successful"],
                        "failed": row["failed"],
                        "success_rate": row["success_rate"]
                    }
                    for row in trend
                ],
                "recent_failures": [
                    {
                        "content_id": row["content_id"],
                        "platform": row["target_platform"],
                        "error": row["error_message"],
                        "run_type": row["run_type"],
                        "agent": row["agent_name"],
                        "created_at": row["created_at"]
                    }
                    for row in recent_failures
                ]
            }
        finally:
            conn.close()
    
    def export_report_json(
        self,
        report_type: str = "outbound",
        output_path: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Export a report to JSON file.
        
        Args:
            report_type: Type of report (daily, weekly, outbound)
            output_path: Output file path (default: auto-generated)
            **kwargs: Arguments passed to report generator
            
        Returns:
            Path to generated file
        """
        if report_type == "daily":
            report = self.generate_daily_report(**kwargs)
        elif report_type == "weekly":
            report = self.generate_weekly_report(**kwargs)
        else:
            report = self.generate_outbound_report(**kwargs)
        
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"syndication_report_{report_type}_{timestamp}.json"
        
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        return output_path
