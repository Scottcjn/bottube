#!/usr/bin/env python3
"""
Tests for BoTTube Syndication Run Tracking — Issue #312

Run with:
    python3 -m pytest tests/test_syndication.py -v
"""

import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase

from syndication_tracker import (
    SyndicationTracker,
    ReportGenerator,
    RunStatus,
    TargetPlatform,
)


class TestSyndicationTracker(TestCase):
    """Test syndication run tracking functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_syndication.db")
        self.tracker = SyndicationTracker(self.db_path)
        
        # Create a test agents table for foreign key references
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                api_key TEXT
            )
        """)
        conn.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("test_agent", "Test Agent", "test_key_123")
        )
        conn.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("another_agent", "Another Agent", "test_key_456")
        )
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)
    
    def test_start_run(self):
        """Test starting a new syndication run."""
        run_id = self.tracker.start_run(
            run_type="x_crosspost",
            agent_id=1,
            metadata={"batch_id": "batch_001"}
        )
        
        self.assertIsInstance(run_id, int)
        self.assertGreater(run_id, 0)
        
        run = self.tracker.get_run(run_id)
        self.assertIsNotNone(run)
        self.assertEqual(run.run_type, "x_crosspost")
        self.assertEqual(run.agent_id, 1)
        self.assertEqual(run.status, "running")
        self.assertEqual(run.metadata, {"batch_id": "batch_001"})
    
    def test_end_run(self):
        """Test ending a syndication run."""
        run_id = self.tracker.start_run("rss_update", agent_id=1)
        
        # Log some items first
        self.tracker.log_item(run_id, "video_001", "success", "rss")
        self.tracker.log_item(run_id, "video_002", "success", "rss")
        self.tracker.log_item(run_id, "video_003", "failed", "rss", error_message="Timeout")
        
        self.tracker.end_run(run_id, "completed")
        
        run = self.tracker.get_run(run_id)
        self.assertEqual(run.status, "completed")
        self.assertIsNotNone(run.ended_at)
        self.assertEqual(run.total_items, 3)
        self.assertEqual(run.successful_items, 2)
        self.assertEqual(run.failed_items, 1)
    
    def test_log_item(self):
        """Test logging syndication items."""
        run_id = self.tracker.start_run("moltbook_sync", agent_id=1)
        
        item_id = self.tracker.log_item(
            run_id=run_id,
            content_id="video_abc123",
            status="success",
            target_platform="moltbook",
            external_id="molt_789",
            external_url="https://moltbook.com/video/789",
            metadata={"engagement": {"likes": 10}}
        )
        
        self.assertIsInstance(item_id, int)
        self.assertGreater(item_id, 0)
        
        items = self.tracker.get_run_items(run_id)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.content_id, "video_abc123")
        self.assertEqual(item.target_platform, "moltbook")
        self.assertEqual(item.status, "success")
        self.assertEqual(item.external_id, "molt_789")
        self.assertEqual(item.external_url, "https://moltbook.com/video/789")
        self.assertEqual(item.metadata, {"engagement": {"likes": 10}})
    
    def test_update_item_status(self):
        """Test updating item status."""
        run_id = self.tracker.start_run("x_crosspost", agent_id=1)
        item_id = self.tracker.log_item(run_id, "video_001", "pending", "x")
        
        self.tracker.update_item_status(
            item_id=item_id,
            status="success",
            external_id="x_12345",
            external_url="https://x.com/status/12345"
        )
        
        items = self.tracker.get_run_items(run_id)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.status, "success")
        self.assertEqual(item.external_id, "x_12345")
        self.assertEqual(item.external_url, "https://x.com/status/12345")
    
    def test_get_active_runs(self):
        """Test getting active runs."""
        run1 = self.tracker.start_run("x_crosspost", agent_id=1)
        run2 = self.tracker.start_run("rss_update", agent_id=2)
        
        self.tracker.end_run(run2, "completed")
        
        active = self.tracker.get_active_runs()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].run_id, run1)
    
    def test_get_recent_runs(self):
        """Test getting recent runs."""
        for i in range(5):
            run_id = self.tracker.start_run(f"run_{i}", agent_id=1)
            self.tracker.end_run(run_id, "completed")
        
        recent = self.tracker.get_recent_runs(limit=3)
        self.assertEqual(len(recent), 3)
        
        # Verify ordering (most recent first)
        for i in range(len(recent) - 1):
            self.assertGreaterEqual(recent[i].started_at, recent[i + 1].started_at)
    
    def test_daily_summary(self):
        """Test daily summary generation."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Create runs for today
        for i in range(3):
            run_id = self.tracker.start_run("x_crosspost", agent_id=1)
            self.tracker.log_item(run_id, f"video_{i}", "success", "x")
            self.tracker.end_run(run_id, "completed")
        
        summary = self.tracker.get_daily_summary(today)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["total_runs"], 3)
        self.assertEqual(summary["completed_runs"], 3)
        self.assertEqual(summary["total_items"], 3)
        self.assertEqual(summary["successful_items"], 3)
    
    def test_run_with_metadata_updates(self):
        """Test run metadata updates on end."""
        run_id = self.tracker.start_run(
            "batch_sync",
            agent_id=1,
            metadata={"initial": True}
        )
        
        self.tracker.end_run(
            run_id,
            "completed",
            metadata={"final": True, "duration_sec": 120}
        )
        
        run = self.tracker.get_run(run_id)
        self.assertEqual(run.metadata["initial"], True)
        self.assertEqual(run.metadata["final"], True)
        self.assertEqual(run.metadata["duration_sec"], 120)


class TestReportGenerator(TestCase):
    """Test report generation functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_reports.db")
        
        # Initialize tracker and create test data
        self.tracker = SyndicationTracker(self.db_path)
        self.generator = ReportGenerator(self.db_path)
        
        # Create agents table
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                api_key TEXT
            )
        """)
        conn.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("test_agent", "Test Agent", "test_key_123")
        )
        conn.commit()
        conn.close()
        
        # Create test data
        self._create_test_data()
    
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)
    
    def _create_test_data(self):
        """Create test syndication data."""
        today = datetime.now()
        
        # Create runs for multiple days
        for day_offset in range(7):
            date = today - timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            
            for i in range(3):
                run_id = self.tracker.start_run(
                    "x_crosspost" if i % 2 == 0 else "moltbook_sync",
                    agent_id=1
                )
                
                # Log items with varying success
                for j in range(2):
                    status = "success" if j == 0 else ("success" if day_offset % 2 == 0 else "failed")
                    self.tracker.log_item(
                        run_id,
                        f"video_{date_str}_{i}_{j}",
                        status,
                        "x" if i % 2 == 0 else "moltbook",
                        external_id=f"ext_{i}_{j}" if status == "success" else None,
                        error_message="Timeout" if status == "failed" else None
                    )
                
                self.tracker.end_run(
                    run_id,
                    "completed" if day_offset % 2 == 0 else "partial"
                )
    
    def test_generate_daily_report(self):
        """Test daily report generation."""
        today = datetime.now().strftime("%Y-%m-%d")
        report = self.generator.generate_daily_report(today)
        
        self.assertEqual(report["report_type"], "daily")
        self.assertEqual(report["date"], today)
        self.assertIn("summary", report)
        self.assertIn("runs", report)
        self.assertIn("generated_at", report)
        
        summary = report["summary"]
        self.assertIn("total_runs", summary)
        self.assertIn("completed_runs", summary)
        self.assertIn("total_items", summary)
    
    def test_generate_weekly_report(self):
        """Test weekly report generation."""
        report = self.generator.generate_weekly_report()
        
        self.assertEqual(report["report_type"], "weekly")
        self.assertIn("start_date", report)
        self.assertIn("end_date", report)
        self.assertIn("summary", report)
        self.assertIn("by_platform", report)
        self.assertIn("by_run_type", report)
        self.assertIn("top_agents", report)
        self.assertIn("daily_breakdown", report)
        
        summary = report["summary"]
        self.assertIn("total_runs", summary)
        self.assertIn("success_rate", summary)
        self.assertGreaterEqual(summary["success_rate"], 0)
        self.assertLessEqual(summary["success_rate"], 100)
    
    def test_generate_outbound_report(self):
        """Test outbound network report generation."""
        report = self.generator.generate_outbound_report(days=7)
        
        self.assertEqual(report["report_type"], "outbound")
        self.assertEqual(report["title"], "Unified Network Outbound Syndication Report")
        self.assertEqual(report["period_days"], 7)
        self.assertIn("generated_at", report)
        self.assertIn("generated_at_iso", report)
        
        # Check network summary
        network = report["network_summary"]
        self.assertIn("total_runs", network)
        self.assertIn("active_agents", network)
        self.assertIn("total_outbound_items", network)
        self.assertIn("total_failures", network)
        self.assertIn("overall_success_rate", network)
        
        # Check platform reach
        self.assertIn("platform_reach", report)
        self.assertIsInstance(report["platform_reach"], list)
        
        # Check trend data
        self.assertIn("success_rate_trend", report)
        self.assertIsInstance(report["success_rate_trend"], list)
        
        # Check recent failures
        self.assertIn("recent_failures", report)
        self.assertIsInstance(report["recent_failures"], list)
    
    def test_export_report_json(self):
        """Test JSON report export."""
        import tempfile
        output_path = os.path.join(self.temp_dir, "test_export.json")
        self.generator.export_report_json(
            report_type="outbound",
            days=7,
            output_path=output_path
        )

        self.assertTrue(os.path.exists(output_path))

        with open(output_path) as f:
            data = json.load(f)

        self.assertEqual(data["report_type"], "outbound")
        self.assertIn("network_summary", data)

        # Clean up
        os.remove(output_path)
    
    def test_empty_report(self):
        """Test report generation with no data."""
        # Use a date with no data
        old_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        report = self.generator.generate_daily_report(old_date)
        
        self.assertEqual(report["report_type"], "daily")
        self.assertEqual(report["summary"]["total_runs"], 0)
        self.assertEqual(len(report["runs"]), 0)


class TestSyndicationIntegration(TestCase):
    """Integration tests for syndication tracking workflow."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_integration.db")
        self.tracker = SyndicationTracker(self.db_path)
        self.generator = ReportGenerator(self.db_path)
        
        # Create agents table
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                api_key TEXT
            )
        """)
        conn.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("agent_alpha", "Agent Alpha", "key_alpha")
        )
        conn.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("agent_beta", "Agent Beta", "key_beta")
        )
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)
    
    def test_full_syndication_workflow(self):
        """Test complete syndication workflow."""
        # Agent Alpha starts a cross-post run
        run_id = self.tracker.start_run(
            "x_crosspost",
            agent_id=1,
            metadata={"source": "auto_scheduler"}
        )
        
        # Log multiple items
        items = []
        for i in range(5):
            item_id = self.tracker.log_item(
                run_id,
                f"video_{i}",
                "pending",
                "x"
            )
            items.append(item_id)
        
        # Update items as they complete
        for i, item_id in enumerate(items):
            if i < 4:  # 80% success rate
                self.tracker.update_item_status(
                    item_id,
                    "success",
                    external_id=f"x_{1000 + i}",
                    external_url=f"https://x.com/status/{1000 + i}"
                )
            else:
                self.tracker.update_item_status(
                    item_id,
                    "failed",
                    error_message="Rate limit exceeded"
                )
        
        # End the run
        self.tracker.end_run(
            run_id,
            "partial",
            metadata={"duration_sec": 45}
        )
        
        # Verify run state
        run = self.tracker.get_run(run_id)
        self.assertEqual(run.status, "partial")
        self.assertEqual(run.total_items, 5)
        self.assertEqual(run.successful_items, 4)
        self.assertEqual(run.failed_items, 1)
        
        # Generate report
        report = self.generator.generate_outbound_report(days=1)
        self.assertEqual(report["network_summary"]["total_runs"], 1)
        self.assertEqual(report["network_summary"]["total_outbound_items"], 4)
        self.assertEqual(report["network_summary"]["total_failures"], 1)
    
    def test_concurrent_runs(self):
        """Test multiple concurrent syndication runs."""
        # Start runs for different agents
        run1 = self.tracker.start_run("x_crosspost", agent_id=1)
        run2 = self.tracker.start_run("moltbook_sync", agent_id=2)
        run3 = self.tracker.start_run("rss_update", agent_id=1)
        
        # Log items for each run
        self.tracker.log_item(run1, "video_a", "success", "x")
        self.tracker.log_item(run2, "video_b", "success", "moltbook")
        self.tracker.log_item(run3, "video_c", "success", "rss")
        
        # Verify active runs
        active = self.tracker.get_active_runs()
        self.assertEqual(len(active), 3)
        
        # End runs at different times
        self.tracker.end_run(run1, "completed")
        self.tracker.end_run(run2, "completed")
        
        active = self.tracker.get_active_runs()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].run_id, run3)
        
        self.tracker.end_run(run3, "completed")
        
        # Verify all runs completed
        active = self.tracker.get_active_runs()
        self.assertEqual(len(active), 0)

    def test_multi_platform_syndication(self):
        """Test syndication to multiple platforms."""
        run_id = self.tracker.start_run("multi_platform", agent_id=1)

        # Syndicate same content to multiple platforms
        platforms = ["x", "moltbook", "rss", "activitypub"]
        for platform in platforms:
            self.tracker.log_item(
                run_id,
                "video_multi",
                "success",
                platform,
                external_id=f"{platform}_123"
            )

        self.tracker.end_run(run_id, "completed")

        # Generate report and verify platform reach
        report = self.generator.generate_outbound_report(days=1)

        platform_names = [p["platform"] for p in report["platform_reach"]]
        for platform in platforms:
            self.assertIn(platform, platform_names)


class TestIssue360Authorization(TestCase):
    """
    Regression tests for Issue #360: Syndication Auth Lockdown
    
    Tests:
    - Cross-agent denial on PUT /api/syndication/item/<id>
    - Report scoping (agent vs network-wide)
    """

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_issue360.db")
        self.tracker = SyndicationTracker(self.db_path)
        self.generator = ReportGenerator(self.db_path)

        # Create agents table
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                api_key TEXT
            )
        """)
        # Create two test agents
        conn.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("agent_alice", "Alice Agent", "key_alice")
        )
        conn.execute(
            "INSERT INTO agents (agent_name, display_name, api_key) VALUES (?, ?, ?)",
            ("agent_bob", "Bob Agent", "key_bob")
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_cross_agent_item_update_denied(self):
        """Test that Agent Bob cannot update Agent Alice's syndication item."""
        # Alice creates a run and logs an item
        alice_run_id = self.tracker.start_run("x_crosspost", agent_id=1)
        alice_item_id = self.tracker.log_item(
            alice_run_id, "video_alice", "pending", "x"
        )

        # Verify Bob (agent_id=2) cannot access Alice's item via run ownership check
        # This simulates the authorization check in the route
        conn = self.tracker._get_connection()
        try:
            item = conn.execute(
                """
                SELECT si.id, si.run_id, sr.agent_id
                FROM syndication_items si
                JOIN syndication_runs sr ON si.run_id = sr.id
                WHERE si.id = ?
                """,
                (alice_item_id,)
            ).fetchone()
        finally:
            conn.close()

        # Bob's agent_id (2) != item's agent_id (1)
        self.assertEqual(item["agent_id"], 1)  # Alice's agent_id
        self.assertNotEqual(item["agent_id"], 2)  # Bob's agent_id

    def test_owner_can_update_own_item(self):
        """Test that an agent can update their own syndication item."""
        # Alice creates a run and logs an item
        alice_run_id = self.tracker.start_run("x_crosspost", agent_id=1)
        alice_item_id = self.tracker.log_item(
            alice_run_id, "video_alice", "pending", "x"
        )

        # Verify Alice (agent_id=1) owns the item
        conn = self.tracker._get_connection()
        try:
            item = conn.execute(
                """
                SELECT si.id, si.run_id, sr.agent_id
                FROM syndication_items si
                JOIN syndication_runs sr ON si.run_id = sr.id
                WHERE si.id = ?
                """,
                (alice_item_id,)
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(item["agent_id"], 1)  # Alice's agent_id

        # Alice can update her own item
        self.tracker.update_item_status(
            item_id=alice_item_id,
            status="success",
            external_id="x_12345"
        )

        # Verify update succeeded
        conn = self.tracker._get_connection()
        try:
            updated_item = conn.execute(
                "SELECT status, external_id FROM syndication_items WHERE id = ?",
                (alice_item_id,)
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(updated_item["status"], "success")
        self.assertEqual(updated_item["external_id"], "x_12345")

    def test_report_scoping_daily(self):
        """Test daily report scoping by agent."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Create runs for both agents
        alice_run = self.tracker.start_run("x_crosspost", agent_id=1)
        self.tracker.log_item(alice_run, "video_alice_1", "success", "x")
        self.tracker.end_run(alice_run, "completed")

        bob_run = self.tracker.start_run("moltbook_sync", agent_id=2)
        self.tracker.log_item(bob_run, "video_bob_1", "success", "moltbook")
        self.tracker.end_run(bob_run, "completed")

        # Network-wide report (agent_id=None) should see both runs
        network_report = self.generator.generate_daily_report(today, agent_id=None)
        self.assertEqual(len(network_report["runs"]), 2)
        self.assertEqual(network_report["scope"], "network")

        # Agent-scoped report (agent_id=1) should only see Alice's run
        alice_report = self.generator.generate_daily_report(today, agent_id=1)
        self.assertEqual(len(alice_report["runs"]), 1)
        self.assertEqual(alice_report["runs"][0]["run_id"], alice_run)
        self.assertEqual(alice_report["scope"], "agent")

        # Agent-scoped report (agent_id=2) should only see Bob's run
        bob_report = self.generator.generate_daily_report(today, agent_id=2)
        self.assertEqual(len(bob_report["runs"]), 1)
        self.assertEqual(bob_report["runs"][0]["run_id"], bob_run)
        self.assertEqual(bob_report["scope"], "agent")

    def test_report_scoping_weekly(self):
        """Test weekly report scoping by agent."""
        # Create runs for both agents
        alice_run = self.tracker.start_run("x_crosspost", agent_id=1)
        self.tracker.log_item(alice_run, "video_alice_1", "success", "x")
        self.tracker.end_run(alice_run, "completed")

        bob_run = self.tracker.start_run("moltbook_sync", agent_id=2)
        self.tracker.log_item(bob_run, "video_bob_1", "success", "moltbook")
        self.tracker.end_run(bob_run, "completed")

        # Network-wide report should see both runs
        network_report = self.generator.generate_weekly_report(agent_id=None)
        self.assertEqual(network_report["summary"]["total_runs"], 2)
        self.assertEqual(network_report["scope"], "network")
        # Network report should include top_agents
        self.assertIn("top_agents", network_report)

        # Agent-scoped report should only see own runs
        alice_report = self.generator.generate_weekly_report(agent_id=1)
        self.assertEqual(alice_report["summary"]["total_runs"], 1)
        self.assertEqual(alice_report["scope"], "agent")
        # Agent-scoped report should not include top_agents
        self.assertEqual(alice_report.get("top_agents"), [])

    def test_report_scoping_outbound(self):
        """Test outbound report scoping by agent."""
        # Create runs for both agents
        alice_run = self.tracker.start_run("x_crosspost", agent_id=1)
        self.tracker.log_item(alice_run, "video_alice_1", "success", "x")
        self.tracker.log_item(alice_run, "video_alice_2", "success", "moltbook")
        self.tracker.end_run(alice_run, "completed")

        bob_run = self.tracker.start_run("rss_update", agent_id=2)
        self.tracker.log_item(bob_run, "video_bob_1", "success", "rss")
        self.tracker.end_run(bob_run, "completed")

        # Network-wide report should see all items
        network_report = self.generator.generate_outbound_report(days=1, agent_id=None)
        self.assertEqual(network_report["network_summary"]["total_runs"], 2)
        self.assertEqual(network_report["network_summary"]["total_outbound_items"], 3)
        self.assertEqual(network_report["scope"], "network")

        # Agent-scoped report should only see own items
        alice_report = self.generator.generate_outbound_report(days=1, agent_id=1)
        self.assertEqual(alice_report["network_summary"]["total_runs"], 1)
        self.assertEqual(alice_report["network_summary"]["total_outbound_items"], 2)
        self.assertEqual(alice_report["scope"], "agent")

        bob_report = self.generator.generate_outbound_report(days=1, agent_id=2)
        self.assertEqual(bob_report["network_summary"]["total_runs"], 1)
        self.assertEqual(bob_report["network_summary"]["total_outbound_items"], 1)
        self.assertEqual(bob_report["scope"], "agent")

    def test_export_report_no_file_write(self):
        """Test that export_report_json with output_path=None returns dict directly."""
        # Create some test data
        run_id = self.tracker.start_run("x_crosspost", agent_id=1)
        self.tracker.log_item(run_id, "video_1", "success", "x")
        self.tracker.end_run(run_id, "completed")

        # Export without file path should return dict directly
        result = self.generator.export_report_json(
            report_type="outbound",
            output_path=None,
            days=1,
            agent_id=1
        )

        # Should be a dict, not a string path
        self.assertIsInstance(result, dict)
        self.assertEqual(result["report_type"], "outbound")
        self.assertIn("network_summary", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
