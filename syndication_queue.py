#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Syndication Queue Module for BoTTube

Manages the syndication queue state machine for distributing new video uploads
to external platforms and partner feeds.

Queue States:
    - pending: Newly queued, awaiting processing
    - processing: Currently being syndicated
    - completed: Successfully syndicated
    - failed: Syndication failed (with error details)
    - cancelled: Manually cancelled before completion

State Transitions:
    pending -> processing -> completed
    pending -> processing -> failed
    pending -> cancelled
    failed -> pending (retry)
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import sqlite3


class QueueState(str, Enum):
    """Syndication queue state machine states."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


VALID_TRANSITIONS = {
    QueueState.PENDING: {QueueState.PROCESSING, QueueState.CANCELLED},
    QueueState.PROCESSING: {QueueState.COMPLETED, QueueState.FAILED},
    QueueState.COMPLETED: set(),  # terminal state
    QueueState.FAILED: {QueueState.PENDING},  # allow retry
    QueueState.CANCELLED: set(),  # terminal state
}


@dataclass
class SyndicationItem:
    """Represents a single syndication queue item."""
    id: Optional[int]
    video_id: str
    video_title: str
    agent_id: int
    agent_name: str
    target_platform: str  # e.g., "moltbook", "twitter", "rss_feed", "partner_api"
    state: QueueState
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    error_message: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    processed_at: Optional[float] = None
    completed_at: Optional[float] = None

    def can_transition_to(self, new_state: QueueState) -> bool:
        """Check if transition to new_state is valid."""
        return new_state in VALID_TRANSITIONS.get(self.state, set())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "video_title": self.video_title,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "target_platform": self.target_platform,
            "state": self.state.value,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "processed_at": self.processed_at,
            "completed_at": self.completed_at,
        }


class SyndicationQueue:
    """
    Manages the syndication queue with SQLite persistence.
    
    Thread-safe operations for adding, updating, and polling queue items.
    """

    def __init__(self, db_path: str):
        """Initialize the instance with default values.
        
        Args:
            db_path: Parameter value.
        """
        self.db_path = db_path
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        """Initialize the syndication queue schema."""
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS syndication_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                video_title TEXT NOT NULL,
                agent_id INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                target_platform TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                error_message TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                processed_at REAL DEFAULT NULL,
                completed_at REAL DEFAULT NULL,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE INDEX IF NOT EXISTS idx_syndication_state 
                ON syndication_queue(state, priority DESC, created_at);

            CREATE INDEX IF NOT EXISTS idx_syndication_video 
                ON syndication_queue(video_id);

            CREATE INDEX IF NOT EXISTS idx_syndication_agent 
                ON syndication_queue(agent_id);

            CREATE INDEX IF NOT EXISTS idx_syndication_platform 
                ON syndication_queue(target_platform, state);
        """)
        conn.commit()
        conn.close()

    def enqueue(
        self,
        video_id: str,
        video_title: str,
        agent_id: int,
        agent_name: str,
        target_platform: str,
        priority: int = 0,
        metadata: Optional[dict] = None,
    ) -> SyndicationItem:
        """
        Add a new item to the syndication queue.
        
        Returns the created SyndicationItem.
        """
        now = time.time()
        metadata_json = json.dumps(metadata or {})
        
        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT INTO syndication_queue
                (video_id, video_title, agent_id, agent_name, target_platform,
                 state, priority, retry_count, max_retries, error_message,
                 metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, 0, 3, '', ?, ?, ?)
            """,
            (video_id, video_title, agent_id, agent_name, target_platform,
             priority, metadata_json, now, now),
        )
        item_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return SyndicationItem(
            id=item_id,
            video_id=video_id,
            video_title=video_title,
            agent_id=agent_id,
            agent_name=agent_name,
            target_platform=target_platform,
            state=QueueState.PENDING,
            priority=priority,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

    def dequeue(self, target_platform: Optional[str] = None) -> Optional[SyndicationItem]:
        """
        Get the next pending item for processing.

        Optionally filter by target platform. Returns the highest priority,
        oldest pending item. Atomically marks the item as processing.
        """
        conn = self._get_connection()
        now = time.time()

        try:
            if target_platform:
                row = conn.execute(
                    """
                    SELECT * FROM syndication_queue
                    WHERE state = 'pending' AND target_platform = ?
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                    """,
                    (target_platform,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM syndication_queue
                    WHERE state = 'pending'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                    """,
                ).fetchone()

            if not row:
                conn.close()
                return None

            item_id = row["id"]

            # Atomically update to processing
            conn.execute(
                """
                UPDATE syndication_queue
                SET state = 'processing', updated_at = ?, processed_at = ?
                WHERE id = ? AND state = 'pending'
                """,
                (now, now, item_id),
            )

            if conn.total_changes == 0:
                # Another process grabbed it
                conn.close()
                return None

            conn.commit()

            # Re-fetch to get updated state
            row = conn.execute(
                "SELECT * FROM syndication_queue WHERE id = ?",
                (item_id,),
            ).fetchone()

            conn.close()
            return self._row_to_item(row)

        except Exception:
            conn.close()
            return None

    def update_state(
        self,
        item_id: int,
        new_state: QueueState,
        error_message: str = "",
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Update an item's state with validation.
        
        Returns True if the transition was valid and successful.
        """
        conn = self._get_connection()
        
        # Get current state
        row = conn.execute(
            "SELECT state, retry_count, metadata FROM syndication_queue WHERE id = ?",
            (item_id,),
        ).fetchone()
        
        if not row:
            conn.close()
            return False
        
        current_state = QueueState(row["state"])
        
        # Validate transition
        if new_state not in VALID_TRANSITIONS.get(current_state, set()):
            conn.close()
            return False
        
        now = time.time()
        updates = ["state = ?", "updated_at = ?"]
        params = [new_state.value, now]
        
        if new_state == QueueState.PROCESSING:
            updates.append("processed_at = ?")
            params.append(now)
        
        if new_state in (QueueState.COMPLETED, QueueState.CANCELLED):
            updates.append("completed_at = ?")
            params.append(now)
        
        if error_message:
            updates.append("error_message = ?")
            params.append(error_message)
        
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))
        
        if new_state == QueueState.PENDING and current_state == QueueState.FAILED:
            # Reset retry count on retry
            updates.append("retry_count = ?")
            params.append(row["retry_count"] + 1)
        
        params.append(item_id)
        
        conn.execute(
            f"UPDATE syndication_queue SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        conn.close()
        
        return True

    def mark_processing(self, item_id: int) -> bool:
        """Mark an item as being processed."""
        return self.update_state(item_id, QueueState.PROCESSING)

    def mark_completed(self, item_id: int, metadata: Optional[dict] = None) -> bool:
        """Mark an item as successfully completed."""
        return self.update_state(item_id, QueueState.COMPLETED, metadata=metadata)

    def mark_failed(
        self,
        item_id: int,
        error_message: str,
        auto_retry: bool = True,
    ) -> bool:
        """
        Mark an item as failed.

        If auto_retry is True and retries remain, resets to pending for retry.
        Note: This requires two transitions: processing -> failed -> pending.
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT state, retry_count, max_retries FROM syndication_queue WHERE id = ?",
            (item_id,),
        ).fetchone()
        conn.close()

        if not row:
            return False

        current_state = QueueState(row["state"])
        retry_count = row["retry_count"]
        max_retries = row["max_retries"]

        # First, transition to failed
        if not self.update_state(item_id, QueueState.FAILED, error_message=error_message):
            return False

        # If retry is enabled and retries remain, transition back to pending
        if auto_retry and retry_count < max_retries:
            now = time.time()
            conn = self._get_connection()
            conn.execute(
                """
                UPDATE syndication_queue
                SET state = 'pending', updated_at = ?, retry_count = retry_count + 1
                WHERE id = ?
                """,
                (now, item_id),
            )
            conn.commit()
            conn.close()
            return True

        return True

    def cancel(self, item_id: int) -> bool:
        """Cancel a pending item."""
        return self.update_state(item_id, QueueState.CANCELLED)

    def get_item(self, item_id: int) -> Optional[SyndicationItem]:
        """Get a specific queue item by ID."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM syndication_queue WHERE id = ?",
            (item_id,),
        ).fetchone()
        conn.close()
        
        if not row:
            return None
        
        return self._row_to_item(row)

    def get_items_by_video(self, video_id: str) -> list[SyndicationItem]:
        """Get all syndication items for a video."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM syndication_queue WHERE video_id = ? ORDER BY created_at",
            (video_id,),
        ).fetchall()
        conn.close()
        
        return [self._row_to_item(row) for row in rows]

    def get_items_by_agent(self, agent_id: int) -> list[SyndicationItem]:
        """Get all syndication items for an agent."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM syndication_queue WHERE agent_id = ? ORDER BY created_at DESC",
            (agent_id,),
        ).fetchall()
        conn.close()
        
        return [self._row_to_item(row) for row in rows]

    def get_pending_count(self, target_platform: Optional[str] = None) -> int:
        """Get count of pending items, optionally filtered by platform."""
        conn = self._get_connection()
        
        if target_platform:
            result = conn.execute(
                "SELECT COUNT(*) FROM syndication_queue WHERE state = 'pending' AND target_platform = ?",
                (target_platform,),
            ).fetchone()[0]
        else:
            result = conn.execute(
                "SELECT COUNT(*) FROM syndication_queue WHERE state = 'pending'",
            ).fetchone()[0]
        
        conn.close()
        return result

    def get_stats(self) -> dict:
        """Get queue statistics."""
        conn = self._get_connection()
        
        stats = {}
        for state in QueueState:
            count = conn.execute(
                "SELECT COUNT(*) FROM syndication_queue WHERE state = ?",
                (state.value,),
            ).fetchone()[0]
            stats[state.value] = count
        
        # Platform breakdown
        platform_stats = conn.execute(
            """
            SELECT target_platform, state, COUNT(*) as count
            FROM syndication_queue
            GROUP BY target_platform, state
            ORDER BY target_platform, state
            """,
        ).fetchall()
        
        stats["by_platform"] = {}
        for row in platform_stats:
            platform = row["target_platform"]
            if platform not in stats["by_platform"]:
                stats["by_platform"][platform] = {}
            stats["by_platform"][platform][row["state"]] = row["count"]
        
        conn.close()
        return stats

    def cleanup_old(self, days: int = 30) -> int:
        """
        Remove completed/cancelled items older than specified days.
        
        Returns the number of rows deleted.
        """
        conn = self._get_connection()
        cutoff = time.time() - (days * 86400)
        
        result = conn.execute(
            """
            DELETE FROM syndication_queue
            WHERE state IN ('completed', 'cancelled')
            AND completed_at < ?
            """,
            (cutoff,),
        )
        deleted = result.rowcount
        conn.commit()
        conn.close()
        
        return deleted

    def _row_to_item(self, row: sqlite3.Row) -> SyndicationItem:
        """Convert a database row to a SyndicationItem."""
        return SyndicationItem(
            id=row["id"],
            video_id=row["video_id"],
            video_title=row["video_title"],
            agent_id=row["agent_id"],
            agent_name=row["agent_name"],
            target_platform=row["target_platform"],
            state=QueueState(row["state"]),
            priority=row["priority"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            error_message=row["error_message"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            processed_at=row["processed_at"],
            completed_at=row["completed_at"],
        )


# Module-level convenience functions for use with the app's DB
_queue_instance: Optional[SyndicationQueue] = None


def get_queue(db_path: str) -> SyndicationQueue:
    """Get or create the syndication queue instance."""
    global _queue_instance
    if _queue_instance is None or _queue_instance.db_path != db_path:
        _queue_instance = SyndicationQueue(db_path)
    return _queue_instance


def queue_syndication(
    db_path: str,
    video_id: str,
    video_title: str,
    agent_id: int,
    agent_name: str,
    target_platform: str,
    priority: int = 0,
    metadata: Optional[dict] = None,
) -> SyndicationItem:
    """Convenience function to queue a syndication item."""
    queue = get_queue(db_path)
    return queue.enqueue(
        video_id, video_title, agent_id, agent_name,
        target_platform, priority, metadata,
    )
