# SPDX-License-Identifier: MIT
"""
Tests for the BoTTube Syndication Queue module.

Run with: pytest tests/test_syndication_queue.py -v
"""

import os
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syndication_queue import (
    QueueState,
    SyndicationItem,
    SyndicationQueue,
    VALID_TRANSITIONS,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database path."""
    return str(tmp_path / "test_syndication.db")


@pytest.fixture
def queue(tmp_db):
    """Create a fresh SyndicationQueue instance."""
    return SyndicationQueue(tmp_db)


@pytest.fixture
def sample_video():
    """Sample video data for testing."""
    return {
        "video_id": "test_video_abc123",
        "video_title": "Test Video Title",
        "agent_id": 42,
        "agent_name": "test_agent",
    }


class TestQueueState:
    """Tests for QueueState enum and transitions."""

    def test_valid_states(self):
        """Test that all expected states exist."""
        assert QueueState.PENDING.value == "pending"
        assert QueueState.PROCESSING.value == "processing"
        assert QueueState.COMPLETED.value == "completed"
        assert QueueState.FAILED.value == "failed"
        assert QueueState.CANCELLED.value == "cancelled"

    def test_valid_transitions(self):
        """Test state transition rules."""
        # pending -> processing, cancelled
        assert QueueState.PROCESSING in VALID_TRANSITIONS[QueueState.PENDING]
        assert QueueState.CANCELLED in VALID_TRANSITIONS[QueueState.PENDING]
        assert QueueState.COMPLETED not in VALID_TRANSITIONS[QueueState.PENDING]
        
        # processing -> completed, failed
        assert QueueState.COMPLETED in VALID_TRANSITIONS[QueueState.PROCESSING]
        assert QueueState.FAILED in VALID_TRANSITIONS[QueueState.PROCESSING]
        assert QueueState.PENDING not in VALID_TRANSITIONS[QueueState.PROCESSING]
        
        # completed is terminal
        assert len(VALID_TRANSITIONS[QueueState.COMPLETED]) == 0
        
        # failed -> pending (retry)
        assert QueueState.PENDING in VALID_TRANSITIONS[QueueState.FAILED]
        
        # cancelled is terminal
        assert len(VALID_TRANSITIONS[QueueState.CANCELLED]) == 0


class TestSyndicationItem:
    """Tests for SyndicationItem dataclass."""

    def test_create_item(self, sample_video):
        """Test creating a SyndicationItem."""
        item = SyndicationItem(
            id=None,
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
            state=QueueState.PENDING,
        )
        
        assert item.video_id == sample_video["video_id"]
        assert item.state == QueueState.PENDING
        assert item.retry_count == 0
        assert item.max_retries == 3
        assert item.priority == 0
        assert item.error_message == ""
        assert item.metadata == {}

    def test_can_transition_to(self, sample_video):
        """Test transition validation on items."""
        item = SyndicationItem(
            id=1,
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
            state=QueueState.PENDING,
        )
        
        assert item.can_transition_to(QueueState.PROCESSING) is True
        assert item.can_transition_to(QueueState.CANCELLED) is True
        assert item.can_transition_to(QueueState.COMPLETED) is False

    def test_to_dict(self, sample_video):
        """Test serialization to dictionary."""
        item = SyndicationItem(
            id=1,
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="twitter",
            state=QueueState.PENDING,
            priority=10,
        )
        
        data = item.to_dict()
        
        assert data["id"] == 1
        assert data["video_id"] == sample_video["video_id"]
        assert data["state"] == "pending"
        assert data["target_platform"] == "twitter"
        assert data["priority"] == 10
        assert "created_at" in data
        assert "updated_at" in data


class _TransitionCursor:
    def __init__(self, *, row=None, rowcount=0):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class _ConcurrentTransitionState:
    def __init__(self):
        self.state = QueueState.PROCESSING.value
        self.reads = threading.Barrier(2)
        self.lock = threading.Lock()


class _ConcurrentTransitionConnection:
    def __init__(self, shared):
        self.shared = shared

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("select state, retry_count, metadata"):
            stale_state = self.shared.state
            self.shared.reads.wait(timeout=2)
            return _TransitionCursor(
                row={"state": stale_state, "retry_count": 0, "metadata": "{}"}
            )
        if normalized.startswith("update syndication_queue set"):
            guarded = "where id = ? and state = ?" in normalized
            expected = params[-1] if guarded else None
            with self.shared.lock:
                if guarded and self.shared.state != expected:
                    return _TransitionCursor(rowcount=0)
                self.shared.state = params[0]
                return _TransitionCursor(rowcount=1)
        raise AssertionError(f"unexpected SQL in transition harness: {normalized}")

    def commit(self):
        return None

    def close(self):
        return None


def test_concurrent_terminal_transitions_have_exactly_one_winner(queue, monkeypatch):
    shared = _ConcurrentTransitionState()
    monkeypatch.setattr(
        queue,
        "_get_connection",
        lambda: _ConcurrentTransitionConnection(shared),
    )
    results = []

    def transition(target):
        results.append(queue.update_state(1, target))

    workers = [
        threading.Thread(target=transition, args=(target,))
        for target in (QueueState.COMPLETED, QueueState.FAILED)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)

    assert all(not worker.is_alive() for worker in workers)
    assert sorted(results) == [False, True]
    assert shared.state in {QueueState.COMPLETED.value, QueueState.FAILED.value}


class TestSyndicationQueue:
    """Tests for SyndicationQueue operations."""

    def test_enqueue(self, queue, sample_video):
        """Test adding an item to the queue."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        
        assert item.id is not None
        assert item.video_id == sample_video["video_id"]
        assert item.state == QueueState.PENDING
        assert item.target_platform == "moltbook"

    def test_enqueue_with_priority(self, queue, sample_video):
        """Test adding an item with custom priority."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="twitter",
            priority=50,
        )
        
        assert item.priority == 50

    def test_enqueue_with_metadata(self, queue, sample_video):
        """Test adding an item with metadata."""
        metadata = {"source": "test", "custom_field": "value"}
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
            metadata=metadata,
        )
        
        assert item.metadata == metadata

    def test_dequeue_empty(self, queue):
        """Test dequeuing from an empty queue."""
        item = queue.dequeue()
        assert item is None

    def test_dequeue(self, queue, sample_video):
        """Test dequeuing an item."""
        queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )

        item = queue.dequeue()

        assert item is not None
        assert item.video_id == sample_video["video_id"]
        assert item.state == QueueState.PROCESSING  # dequeue marks as processing

    def test_dequeue_by_platform(self, queue, sample_video):
        """Test dequeuing items filtered by platform."""
        queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        queue.enqueue(
            video_id="video_2",
            video_title="Video 2",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="twitter",
        )
        
        # Dequeue only moltbook items
        item = queue.dequeue(target_platform="moltbook")
        assert item is not None
        assert item.target_platform == "moltbook"
        
        # No more moltbook items
        item = queue.dequeue(target_platform="moltbook")
        assert item is None

    def test_dequeue_priority_order(self, queue, sample_video):
        """Test that dequeue returns highest priority first."""
        queue.enqueue(
            video_id="low_priority",
            video_title="Low Priority",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
            priority=10,
        )
        queue.enqueue(
            video_id="high_priority",
            video_title="High Priority",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
            priority=100,
        )
        queue.enqueue(
            video_id="medium_priority",
            video_title="Medium Priority",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
            priority=50,
        )
        
        # Should get high priority first
        item = queue.dequeue()
        assert item.video_id == "high_priority"
        
        item = queue.dequeue()
        assert item.video_id == "medium_priority"
        
        item = queue.dequeue()
        assert item.video_id == "low_priority"

    def test_dequeue_fifo_same_priority(self, queue, sample_video):
        """Test FIFO ordering for same priority items."""
        queue.enqueue(
            video_id="first",
            video_title="First",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        time.sleep(0.01)  # Ensure different timestamps
        queue.enqueue(
            video_id="second",
            video_title="Second",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        
        item = queue.dequeue()
        assert item.video_id == "first"
        
        item = queue.dequeue()
        assert item.video_id == "second"

    def test_mark_processing(self, queue, sample_video):
        """Test marking an item as processing."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        
        result = queue.mark_processing(item.id)
        assert result is True
        
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.PROCESSING
        assert updated.processed_at is not None

    def test_mark_completed(self, queue, sample_video):
        """Test marking an item as completed."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        queue.mark_processing(item.id)
        
        metadata = {"external_id": "ext_123"}
        result = queue.mark_completed(item.id, metadata=metadata)
        assert result is True
        
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.COMPLETED
        assert updated.completed_at is not None
        assert updated.metadata.get("external_id") == "ext_123"

    def test_mark_failed_no_retry(self, queue, sample_video):
        """Test marking an item as failed without retry."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        queue.mark_processing(item.id)
        
        result = queue.mark_failed(item.id, "Test error", auto_retry=False)
        assert result is True
        
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.FAILED
        assert updated.error_message == "Test error"

    def test_mark_failed_with_retry(self, queue, sample_video):
        """Test that failed items are retried automatically."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        queue.mark_processing(item.id)
        
        # First failure - should retry
        queue.mark_failed(item.id, "First error", auto_retry=True)
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.PENDING
        assert updated.retry_count == 1
        assert updated.error_message == "First error"
        
        # Process and fail again
        queue.mark_processing(item.id)
        queue.mark_failed(item.id, "Second error", auto_retry=True)
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.PENDING
        assert updated.retry_count == 2
        
        # Continue until max retries exceeded
        for i in range(2):
            queue.mark_processing(item.id)
            queue.mark_failed(item.id, f"Error {i+3}", auto_retry=True)
        
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.FAILED
        assert updated.retry_count == 3

    def test_cancel(self, queue, sample_video):
        """Test cancelling a pending item."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        
        result = queue.cancel(item.id)
        assert result is True
        
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.CANCELLED
        assert updated.completed_at is not None

    def test_invalid_transition(self, queue, sample_video):
        """Test that invalid transitions are rejected."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        
        # Can't go from pending directly to completed
        result = queue.update_state(item.id, QueueState.COMPLETED)
        assert result is False
        
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.PENDING

    def test_get_items_by_video(self, queue, sample_video):
        """Test getting all items for a video."""
        queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="twitter",
        )
        
        items = queue.get_items_by_video(sample_video["video_id"])
        assert len(items) == 2
        
        platforms = {item.target_platform for item in items}
        assert platforms == {"moltbook", "twitter"}

    def test_get_items_by_agent(self, queue, sample_video):
        """Test getting all items for an agent."""
        queue.enqueue(
            video_id="video1",
            video_title="Video 1",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        queue.enqueue(
            video_id="video2",
            video_title="Video 2",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="twitter",
        )
        queue.enqueue(
            video_id="video3",
            video_title="Video 3",
            agent_id=999,
            agent_name="other_agent",
            target_platform="moltbook",
        )
        
        items = queue.get_items_by_agent(sample_video["agent_id"])
        assert len(items) == 2

    def test_get_pending_count(self, queue, sample_video):
        """Test getting pending item count."""
        queue.enqueue(
            video_id="video1",
            video_title="Video 1",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        queue.enqueue(
            video_id="video2",
            video_title="Video 2",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        queue.enqueue(
            video_id="video3",
            video_title="Video 3",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="twitter",
        )
        
        assert queue.get_pending_count() == 3
        assert queue.get_pending_count(target_platform="moltbook") == 2
        assert queue.get_pending_count(target_platform="twitter") == 1

    def test_get_stats(self, queue, sample_video):
        """Test getting queue statistics."""
        queue.enqueue(
            video_id="video1",
            video_title="Video 1",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        queue.enqueue(
            video_id="video2",
            video_title="Video 2",
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="twitter",
        )
        
        stats = queue.get_stats()
        
        assert "pending" in stats
        assert stats["pending"] == 2
        assert "by_platform" in stats
        assert "moltbook" in stats["by_platform"]
        assert "twitter" in stats["by_platform"]

    def test_cleanup_old(self, queue, sample_video):
        """Test cleaning up old completed items."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        queue.mark_processing(item.id)
        queue.mark_completed(item.id)
        
        # Manually set old completed_at for testing
        old_time = time.time() - (31 * 86400)  # 31 days ago
        conn = queue._get_connection()
        conn.execute(
            "UPDATE syndication_queue SET completed_at = ? WHERE id = ?",
            (old_time, item.id),
        )
        conn.commit()
        conn.close()
        
        deleted = queue.cleanup_old(days=30)
        assert deleted == 1
        
        # Verify item is gone
        assert queue.get_item(item.id) is None


class TestStateTransitions:
    """Integration tests for complete state transition flows."""

    def test_happy_path(self, queue, sample_video):
        """Test successful syndication flow."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        
        # pending -> processing
        assert queue.mark_processing(item.id) is True
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.PROCESSING
        
        # processing -> completed
        assert queue.mark_completed(item.id) is True
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.COMPLETED

    def test_retry_flow(self, queue, sample_video):
        """Test flow with retries before success."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        
        # First attempt fails
        queue.mark_processing(item.id)
        queue.mark_failed(item.id, "Temporary error", auto_retry=True)
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.PENDING
        assert updated.retry_count == 1
        
        # Second attempt succeeds
        queue.mark_processing(item.id)
        queue.mark_completed(item.id)
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.COMPLETED
        assert updated.retry_count == 1

    def test_cancel_flow(self, queue, sample_video):
        """Test cancellation flow."""
        item = queue.enqueue(
            video_id=sample_video["video_id"],
            video_title=sample_video["video_title"],
            agent_id=sample_video["agent_id"],
            agent_name=sample_video["agent_name"],
            target_platform="moltbook",
        )
        
        # Cancel while pending
        assert queue.cancel(item.id) is True
        updated = queue.get_item(item.id)
        assert updated.state == QueueState.CANCELLED
        
        # Can't process cancelled item
        assert queue.mark_processing(item.id) is False
