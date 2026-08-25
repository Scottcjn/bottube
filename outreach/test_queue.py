#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unit tests for the syndication queue logic."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from poll_upload_queue import Video, QueueEntry, SyndicationQueue


class TestVideo(unittest.TestCase):
    def test_opt_out_tag_nosyndicate(self):
        """The 'nosyndicate' tag triggers the syndication opt-out."""
        v = Video("v1", "Test", "agent1", "2026-01-01", tags=["nosyndicate"])
        self.assertTrue(v.has_opt_out_tag())

    def test_opt_out_tag_mixed_case(self):
        """The opt-out tag match is case-insensitive."""
        v = Video("v2", "Test", "agent1", "2026-01-01", tags=["NoSyndicate", "game"])
        self.assertTrue(v.has_opt_out_tag())

    def test_no_opt_out(self):
        """Videos without the opt-out tag are not opted out."""
        v = Video("v3", "Test", "agent1", "2026-01-01", tags=["ai", "demo"])
        self.assertFalse(v.has_opt_out_tag())

    def test_empty_tags(self):
        """Videos with no tags are not opted out."""
        v = Video("v4", "Test", "agent1", "2026-01-01", tags=[])
        self.assertFalse(v.has_opt_out_tag())

    def test_from_api(self):
        """Video.from_api builds a Video from the API payload shape."""
        data = {
            "video_id": "vid123",
            "title": "My Video",
            "agent_name": "bot1",
            "created_at": "2026-03-29T12:00:00Z",
            "tags": ["ai"],
        }
        v = Video.from_api(data)
        self.assertEqual(v.video_id, "vid123")
        self.assertEqual(v.title, "My Video")
        self.assertEqual(v.agent_name, "bot1")
        self.assertEqual(v.url, "https://bottube.ai/video/vid123")


class TestSyndicationQueue(unittest.TestCase):
    def setUp(self):
        """Create a temp directory for queue and state files."""
        self.tmpdir = tempfile.mkdtemp()
        self.queue_file = os.path.join(self.tmpdir, "queue.json")
        self.state_file = os.path.join(self.tmpdir, "state.json")

    def tearDown(self):
        """Remove temp queue/state files after each test."""
        for f in [self.queue_file, self.state_file]:
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(self.tmpdir)

    def test_enqueue_new_video(self):
        """A new video is enqueued for syndication."""
        q = SyndicationQueue(self.queue_file, self.state_file)
        v = Video("v1", "Test Video", "agent1", "2026-01-01")
        result = q.enqueue(v)
        self.assertTrue(result)
        self.assertEqual(q.size(), 1)

    def test_dedupe_already_processed(self):
        """Already-processed videos are not re-enqueued."""
        q = SyndicationQueue(self.queue_file, self.state_file)
        v = Video("v1", "Test Video", "agent1", "2026-01-01")
        q.mark_processed("v1")
        result = q.enqueue(v)
        self.assertFalse(result)
        self.assertEqual(q.size(), 0)

    def test_dedupe_already_queued(self):
        """Videos already in the queue are not duplicated."""
        q = SyndicationQueue(self.queue_file, self.state_file)
        v = Video("v1", "Test Video", "agent1", "2026-01-01")
        q.enqueue(v)
        result = q.enqueue(v)  # second call
        self.assertFalse(result)
        self.assertEqual(q.size(), 1)

    def test_opt_out_skipped(self):
        """Opted-out videos are skipped during enqueue."""
        q = SyndicationQueue(self.queue_file, self.state_file)
        v = Video("v1", "Test", "agent1", "2026-01-01", tags=["nosyndicate"])
        result = q.enqueue(v)
        self.assertFalse(result)  # skipped
        self.assertEqual(q.size(), 0)
        self.assertIn("v1", q._processed_ids)

    def test_persistence_across_restarts(self):
        """Queue state survives a full object reload from disk."""
        q1 = SyndicationQueue(self.queue_file, self.state_file)
        v = Video("v1", "Test", "agent1", "2026-01-01")
        q1.enqueue(v)
        q1.mark_processed("v1")

        # New instance reads from disk
        q2 = SyndicationQueue(self.queue_file, self.state_file)
        self.assertEqual(q2.size(), 0)
        self.assertEqual(q2.processed_count(), 1)
        self.assertIn("v1", q2._processed_ids)

    def test_get_pending(self):
        """get_pending returns queued videos not yet processed."""
        q = SyndicationQueue(self.queue_file, self.state_file)
        q.enqueue(Video("v1", "T1", "a", "2026-01-01"))
        q.enqueue(Video("v2", "T2", "a", "2026-01-01"))
        pending = q.get_pending()
        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0].video_id, "v1")
        self.assertEqual(pending[1].video_id, "v2")

    def test_mark_processed_removes_from_queue(self):
        """mark_processed removes the video from the pending queue."""
        q = SyndicationQueue(self.queue_file, self.state_file)
        v = Video("v1", "Test", "agent1", "2026-01-01")
        q.enqueue(v)
        self.assertEqual(q.size(), 1)
        q.mark_processed("v1")
        self.assertEqual(q.size(), 0)
        self.assertIn("v1", q._processed_ids)


if __name__ == "__main__":
    unittest.main()
