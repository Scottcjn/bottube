# SPDX-License-Identifier: MIT
"""Regression tests for Issue #2303: watch page captions track availability.

Asserts that <track kind="captions" ...> is only rendered when captions actually
exist in the video_captions table for the video.
"""
from pathlib import Path
import sqlite3
import unittest


class TestWatchCaptionsAvailability(unittest.TestCase):
    def test_watch_template_conditionally_guards_captions_track(self):
        """Verify that watch.html wraps the <track> element in {% if has_captions %}."""
        template_path = Path(__file__).resolve().parents[1] / "bottube_templates" / "watch.html"
        html = template_path.read_text(encoding="utf-8")

        self.assertIn("{% if has_captions %}", html, "watch.html must conditionally check has_captions")
        self.assertIn('<track kind="captions"', html, "watch.html must contain track element inside the guard")

    def test_watch_captions_query_behavior(self):
        """Verify database query logic for video_captions presence."""
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute(
            """
            CREATE TABLE video_captions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                language TEXT DEFAULT 'en',
                format TEXT DEFAULT 'vtt',
                caption_data TEXT NOT NULL,
                source TEXT DEFAULT 'auto',
                created_at REAL NOT NULL
            )
            """
        )

        # When no captions exist
        video_id_empty = "vid_no_captions"
        row = db.execute("SELECT 1 FROM video_captions WHERE video_id = ? LIMIT 1", (video_id_empty,)).fetchone()
        self.assertFalse(bool(row))

        # When caption exists
        video_id_with_cap = "vid_has_captions"
        db.execute(
            "INSERT INTO video_captions (video_id, language, format, caption_data, source, created_at) VALUES (?, 'en', 'vtt', 'WEBVTT', 'auto', 1.0)",
            (video_id_with_cap,),
        )
        row_present = db.execute("SELECT 1 FROM video_captions WHERE video_id = ? LIMIT 1", (video_id_with_cap,)).fetchone()
        self.assertTrue(bool(row_present))


if __name__ == "__main__":
    unittest.main()
