#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Regression tests for #2161: syndication terminal-state overwrite race.

The pre-fix ``SyndicationQueue.update_state()`` validated the source state
in Python and then issued ``UPDATE ... WHERE id = ?`` with no state
predicate.  Two workers that both observed the same ``processing`` row
could each validate their own transition (``processing -> completed`` and
``processing -> failed``) and both write — last writer wins.

After the fix, the source state is part of the WHERE clause, so the
loser observes ``rowcount == 0`` and ``update_state()`` returns False
without overwriting the winner.  ``mark_failed()``'s retry hop is
protected by the same compare-and-set on the just-written ``failed``
state.
"""

import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from syndication_queue import QueueState, SyndicationQueue  # noqa: E402


def _new_queue() -> SyndicationQueue:
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    return SyndicationQueue(path), path


def _enqueue_processing(q: SyndicationQueue) -> int:
    item = q.enqueue(
        video_id="v2161",
        video_title="race",
        agent_id=1,
        agent_name="a",
        target_platform="x",
    )
    # Move the row to processing synchronously so both racers see the
    # same validated source state.
    assert q.update_state(item.id, QueueState.PROCESSING) is True
    return item.id


class TestUpdateStateCAS(unittest.TestCase):
    """Compare-and-set: one winner, one loser, no overwrites."""

    def test_terminal_transition_race_exactly_one_wins(self):
        q, path = _new_queue()
        try:
            item_id = _enqueue_processing(q)

            barrier = threading.Barrier(2)
            results: dict = {}

            def _do(label, target):
                # Each racer needs its own connection to exercise the
                # multi-writer scenario described in the bug report.
                local = SyndicationQueue(path)
                barrier.wait()  # synchronize the stale-snapshot read
                # We rely on a fresh transition; the bug is that
                # `update_state` accepts two terminal transitions from
                # the same source state and lets both commit.
                ok = local.update_state(item_id, target)
                results[label] = ok

            with ThreadPoolExecutor(max_workers=2) as pool:
                f1 = pool.submit(_do, "completed", QueueState.COMPLETED)
                f2 = pool.submit(_do, "failed", QueueState.FAILED)
                f1.result(timeout=10)
                f2.result(timeout=10)

            self.assertEqual(
                sorted(results.values()),
                [False, True],
                f"Expected exactly one True and one False, got {results}",
            )

            row = q.get_item(item_id)
            self.assertIn(
                row.state,
                (QueueState.COMPLETED, QueueState.FAILED),
                "Row must end in a terminal state",
            )
        finally:
            os.unlink(path)

    def test_loser_does_not_overwrite_winner_terminal_state(self):
        q, path = _new_queue()
        try:
            item_id = _enqueue_processing(q)
            # The winner commits `processing -> completed` first; the
            # loser's later `processing -> failed` MUST be rejected.
            self.assertTrue(q.update_state(item_id, QueueState.COMPLETED))

            loser = SyndicationQueue(path)
            self.assertFalse(
                loser.update_state(item_id, QueueState.FAILED, error_message="late"),
                "Late terminal write must lose the CAS",
            )

            row = q.get_item(item_id)
            self.assertEqual(row.state, QueueState.COMPLETED)
            self.assertNotEqual(row.error_message, "late")
            self.assertIsNotNone(row.completed_at)
        finally:
            os.unlink(path)

    def test_pending_to_processing_cas_keeps_dequeue_safe(self):
        """The existing pending->processing hop must still be single-writer."""
        q, path = _new_queue()
        try:
            item = q.enqueue(
                video_id="v2161d",
                video_title="d",
                agent_id=1,
                agent_name="a",
                target_platform="x",
            )

            barrier = threading.Barrier(3)
            results: list = []

            def _claim():
                local = SyndicationQueue(path)
                barrier.wait()
                results.append(local.update_state(item.id, QueueState.PROCESSING))

            with ThreadPoolExecutor(max_workers=3) as pool:
                futs = [pool.submit(_claim) for _ in range(3)]
                for f in futs:
                    f.result(timeout=10)

            self.assertEqual(
                results.count(True), 1, f"Expected 1 winner, got {results}"
            )
            self.assertEqual(results.count(False), 2)
        finally:
            os.unlink(path)


class TestMarkFailedRetryCAS(unittest.TestCase):
    """mark_failed's failed->pending retry hop must not race itself."""

    def test_mark_failed_retry_only_commits_for_winner(self):
        q, path = _new_queue()
        try:
            item = q.enqueue(
                video_id="v2161r",
                video_title="r",
                agent_id=1,
                agent_name="a",
                target_platform="x",
            )
            self.assertTrue(q.update_state(item.id, QueueState.PROCESSING))

            # First mark_failed is the winner: processing -> failed -> pending
            self.assertTrue(
                q.mark_failed(item.id, error_message="boom", auto_retry=True)
            )
            row = q.get_item(item.id)
            self.assertEqual(row.state, QueueState.PENDING)
            self.assertEqual(row.retry_count, 1)

            # A second mark_failed call on the same item from a stale
            # `processing` snapshot must NOT advance retry_count again
            # and must NOT bounce the row out of pending.
            stale = SyndicationQueue(path)
            # Simulate a worker that still believes the row is `processing`
            # by going through update_state directly (it will be rejected
            # because state is now pending, not processing).  This is the
            # contract the fix enforces.
            ok = stale.update_state(item.id, QueueState.FAILED, error_message="late")
            self.assertFalse(ok, "Stale-snapshot writer must lose the CAS")

            row = q.get_item(item.id)
            self.assertEqual(row.state, QueueState.PENDING)
            self.assertEqual(row.retry_count, 1)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
