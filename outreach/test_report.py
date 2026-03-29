#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unit tests for syndication reporter."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from syndication_report import (
    SyndicationLogger,
    SyndicationRun,
    SyndicationResult,
    format_cli_report,
    format_json_report,
    format_html_report,
)


class TestSyndicationLogger(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.dir, "runs.json")

    def tearDown(self):
        for f in [self.log_file]:
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(self.dir)

    def test_log_and_retrieve(self):
        logger = SyndicationLogger(self.log_file)
        run = SyndicationRun(
            run_id="r1", timestamp="2026-03-29T12:00:00Z",
            videos_detected=10, videos_queued=8, videos_processed=7,
            videos_skipped=1, platforms={"moltbook": {"posted": 5, "failed": 1, "pending": 2}},
            errors=["timeout on x.com"], duration_ms=1200,
        )
        logger.log_run(run)
        runs = logger.get_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].run_id, "r1")
        self.assertEqual(runs[0].videos_detected, 10)

    def test_aggregate_stats(self):
        logger = SyndicationLogger(self.log_file)
        for i in range(3):
            run = SyndicationRun(
                run_id=f"r{i}", timestamp="2026-03-29T12:00:00Z",
                videos_detected=10, videos_queued=8, videos_processed=7,
                videos_skipped=1, platforms={}, errors=[], duration_ms=1000,
            )
            logger.log_run(run)
        stats = logger.get_total_stats()
        self.assertEqual(stats["runs"], 3)
        self.assertEqual(stats["detected"], 30)
        self.assertEqual(stats["processed"], 21)

    def test_platform_stats(self):
        logger = SyndicationLogger(self.log_file)
        run = SyndicationRun(
            run_id="r1", timestamp="2026-03-29T12:00:00Z",
            videos_detected=5, videos_queued=4, videos_processed=3,
            videos_skipped=1,
            platforms={"moltbook": {"posted": 3, "failed": 0, "pending": 1}, "x": {"posted": 1, "failed": 1, "pending": 0}},
            errors=[], duration_ms=800,
        )
        logger.log_run(run)
        pstats = logger.get_platform_stats()
        self.assertEqual(pstats["moltbook"]["posted"], 3)
        self.assertEqual(pstats["x"]["failed"], 1)

    def test_persistence(self):
        logger1 = SyndicationLogger(self.log_file)
        logger1.log_run(SyndicationRun(
            run_id="r1", timestamp="2026-03-29T12:00:00Z",
            videos_detected=10, videos_queued=8, videos_processed=7,
            videos_skipped=1, platforms={}, errors=[], duration_ms=1000,
        ))
        logger2 = SyndicationLogger(self.log_file)
        self.assertEqual(logger2.get_total_stats()["runs"], 1)
        self.assertEqual(logger2.get_total_stats()["detected"], 10)


class TestFormatters(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.dir, "runs.json")
        logger = SyndicationLogger(self.log_file)
        for i in range(2):
            logger.log_run(SyndicationRun(
                run_id=f"r{i}", timestamp="2026-03-29T12:00:00Z",
                videos_detected=10, videos_queued=8, videos_processed=7,
                videos_skipped=1,
                platforms={"moltbook": {"posted": 5, "failed": 1, "pending": 2}},
                errors=[], duration_ms=1000,
            ))

    def tearDown(self):
        if os.path.exists(self.log_file):
            os.remove(self.log_file)
        os.rmdir(self.dir)

    def test_cli_report_contains_stats(self):
        logger = SyndicationLogger(self.log_file)
        report = format_cli_report(logger)
        self.assertIn("Total runs:", report)
        self.assertIn("Videos detected:", report)
        self.assertIn("moltbook", report)

    def test_json_report_valid(self):
        logger = SyndicationLogger(self.log_file)
        report = format_json_report(logger)
        import json
        data = json.loads(report)
        self.assertEqual(data["total_stats"]["runs"], 2)
        self.assertIn("moltbook", data["platform_stats"])

    def test_html_report_valid(self):
        logger = SyndicationLogger(self.log_file)
        report = format_html_report(logger)
        self.assertIn("<html>", report)
        self.assertIn("Syndication Report", report)


if __name__ == "__main__":
    unittest.main()
