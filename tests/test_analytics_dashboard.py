# SPDX-License-Identifier: MIT
"""
Tests for Creator Analytics Dashboard (issue #423).
Tests cover:
- Analytics page access control
- Analytics API endpoint with various data scenarios
- Empty states for new users
- Core metrics calculation (views, engagement, top videos, trend)
"""

import os
import csv
import io
import sqlite3
import sys
import time
from pathlib import Path

import pytest
import werkzeug


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "test"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_bootstrap_db_path = f"/tmp/bottube_test_analytics_{os.getpid()}.db"
os.environ.setdefault("BOTTUBE_DB_PATH", _bootstrap_db_path)
os.environ.setdefault("BOTTUBE_DB", _bootstrap_db_path)

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    Path(bootstrap_path).unlink(missing_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Create test client with fresh database."""
    db_path = tmp_path / "bottube_analytics.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test-admin", raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name, api_key, is_human=False):
    """Insert a test agent and return their ID."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, 1 if is_human else 0, 1.0, 1.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _login(client, agent_name):
    """Log in as the given agent."""
    agent = _lookup_agent(agent_name)
    with client.session_transaction() as sess:
        sess["user_id"] = agent["id"]


def _lookup_agent(agent_name):
    """Look up an agent by name."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        row = db.execute("SELECT * FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
        assert row is not None
        return row


def _insert_video(agent_id, video_id, title=None, created_at=None):
    """Insert a test video."""
    if created_at is None:
        created_at = time.time()
    if title is None:
        title = "Test Video " + video_id
    
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, title, video_id + ".mp4", created_at),
        )
        db.commit()
    return video_id


def _insert_view(video_id, ip="127.0.0.1", created_at=None):
    """Insert a test view."""
    if created_at is None:
        created_at = time.time()
    
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO views (video_id, ip_address, created_at)
            VALUES (?, ?, ?)
            """,
            (video_id, ip, created_at),
        )
        # Also update the cached view count in videos table
        db.execute(
            """
            UPDATE videos SET views = views + 1 WHERE video_id = ?
            """,
            (video_id,),
        )
        db.commit()


def _insert_comment(video_id, agent_id, created_at=None):
    """Insert a test comment for a public video id."""
    if created_at is None:
        created_at = time.time()

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, created_at)
            VALUES (?, ?, 'analytics comment', ?)
            """,
            (video_id, agent_id, created_at),
        )
        db.commit()


def _insert_vote(video_id, agent_id, vote=1, created_at=None):
    """Insert a test vote for a public video id."""
    if created_at is None:
        created_at = time.time()

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO votes (agent_id, video_id, vote, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (agent_id, video_id, vote, created_at),
        )
        db.commit()


def _insert_earning(agent_id, amount, reason, video_id, created_at=None):
    """Insert a test earning for a public video id."""
    if created_at is None:
        created_at = time.time()

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO earnings (agent_id, amount, reason, video_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, amount, reason, video_id, created_at),
        )
        db.commit()


# =============================================================================
# Analytics Page Access Tests
# =============================================================================

class TestAnalyticsPageAccess:
    """Test analytics page access control."""

    def test_analytics_page_requires_login(self, client):
        """Unauthenticated users should be redirected to login."""
        response = client.get("/analytics", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.location

    def test_analytics_page_accessible_when_logged_in(self, client):
        """Logged in users should access analytics page."""
        aid = _insert_agent("testuser", "test-key-123")
        _login(client, "testuser")
        
        response = client.get("/analytics")
        assert response.status_code == 200
        assert b"Creator Analytics" in response.data


# =============================================================================
# Analytics API Tests - Empty State
# =============================================================================

class TestAnalyticsApiEmptyState:
    """Test analytics API for users with no data."""

    def test_analytics_api_empty_for_new_user(self, client):
        """New users with no videos should get empty analytics."""
        _insert_agent("newuser", "test-key-456")
        _login(client, "newuser")
        
        response = client.get("/api/dashboard/analytics?days=30")
        assert response.status_code == 200
        
        data = response.get_json()
        assert data is not None
        assert data["totals"]["views"] == 0
        assert data["totals"]["videos"] == 0
        assert data["totals"]["engagement_rate"] == 0.0
        assert len(data["top_videos"]) == 0

    def test_analytics_api_requires_login(self, client):
        """Analytics API should require authentication."""
        response = client.get("/api/dashboard/analytics")
        assert response.status_code == 401


# =============================================================================
# Analytics API Tests - Core Metrics
# =============================================================================

class TestAnalyticsApiCoreMetrics:
    """Test analytics API core metrics calculation."""

    def test_analytics_api_view_count(self, client):
        """Analytics should correctly count views."""
        now = time.time()
        aid = _insert_agent("viewtest", "test-key-views")
        _login(client, "viewtest")
        
        # Create video and add views
        vid = _insert_video(aid, "vid-001", "Test Video")
        for i in range(5):
            _insert_view(vid, "192.168.1." + str(i), created_at=now - i * 86400)
        
        response = client.get("/api/dashboard/analytics?days=30")
        data = response.get_json()
        
        assert data["totals"]["views"] == 5

    def test_analytics_api_video_count(self, client):
        """Analytics should count videos correctly."""
        aid = _insert_agent("videotest", "test-key-vids")
        _login(client, "videotest")
        
        # Create 5 videos
        for i in range(5):
            _insert_video(aid, "vid-" + str(i).zfill(3), "Video " + str(i))
        
        response = client.get("/api/dashboard/analytics?days=30")
        data = response.get_json()
        
        assert data["totals"]["videos"] == 5

    def test_creator_analytics_blueprint_uses_public_video_ids(self, client):
        """Blueprint analytics should count events stored by public video_id."""
        now = time.time()
        owner_id = _insert_agent("blueprintowner", "test-key-blueprint-owner")
        commenter_one_id = _insert_agent("blueprintcommenter1", "test-key-blueprint-commenter-1")
        commenter_two_id = _insert_agent("blueprintcommenter2", "test-key-blueprint-commenter-2")
        unrelated_id = _insert_agent("blueprintunrelated", "test-key-blueprint-unrelated")
        video_id = _insert_video(owner_id, "public-analytics-clip", "Public ID Analytics")

        _insert_view(video_id, "10.0.0.1", created_at=now)
        _insert_view(video_id, "10.0.0.2", created_at=now)
        _insert_comment(video_id, commenter_one_id, created_at=now)
        _insert_vote(video_id, commenter_one_id, vote=1, created_at=now)
        _insert_vote(video_id, commenter_two_id, vote=1, created_at=now)
        _insert_earning(owner_id, 0.25, "tip_received", video_id, created_at=now)
        _insert_earning(owner_id, 0.25, "tip_received", video_id, created_at=now)
        _insert_earning(unrelated_id, 9.0, "tip_received", video_id, created_at=now)

        views = client.get(f"/analytics/api/views?agent_id={owner_id}&period=7d")
        filtered_views = client.get(
            f"/analytics/api/views?agent_id={owner_id}&video_id={video_id}&period=7d"
        )
        engagement = client.get(f"/analytics/api/engagement?agent_id={owner_id}&period=7d")
        top = client.get(f"/analytics/api/top-videos?agent_id={owner_id}&metric=engagement")
        audience = client.get(f"/analytics/api/audience?agent_id={owner_id}")
        summary = client.get(f"/analytics/api/summary?agent_id={owner_id}")
        export = client.get(f"/analytics/api/export/csv?agent_id={owner_id}&type=videos")

        assert views.status_code == 200
        assert views.get_json()["total_views"] == 2
        assert filtered_views.status_code == 200
        assert filtered_views.get_json()["total_views"] == 2

        assert engagement.status_code == 200
        engagement_body = engagement.get_json()
        assert engagement_body["total_comments"] == 1
        assert engagement_body["total_votes"] == 2
        assert engagement_body["total_tips"] == 0.5
        assert engagement_body["by_video"][0]["video_id"] == video_id
        assert engagement_body["by_video"][0]["comments"] == 1
        assert engagement_body["by_video"][0]["votes"] == 2
        assert engagement_body["by_video"][0]["tips"] == 0.5

        assert top.status_code == 200
        top_video = top.get_json()["videos"][0]
        assert top_video["video_id"] == video_id
        assert top_video["views"] == 2
        assert top_video["comments"] == 1
        assert top_video["votes"] == 2
        assert top_video["tips"] == 0.5

        assert audience.status_code == 200
        assert audience.get_json()["human_viewers"] == 2

        assert summary.status_code == 200
        assert summary.get_json()["total_views"] == 2

        assert export.status_code == 200
        export_rows = list(csv.DictReader(io.StringIO(export.get_data(as_text=True))))
        assert export_rows[0]["video_id"] == video_id
        assert export_rows[0]["views"] == "2"
        assert export_rows[0]["comments"] == "1"
        assert export_rows[0]["votes"] == "2"
        assert export_rows[0]["tips_rtc"] == "0.5"


# =============================================================================
# Analytics API Tests - Time Series Data
# =============================================================================

class TestAnalyticsApiTimeSeries:
    """Test analytics API time series data."""

    def test_analytics_api_daily_views_series(self, client):
        """Analytics should provide daily views time series."""
        now = time.time()
        aid = _insert_agent("seriesuser", "test-key-series")
        _login(client, "seriesuser")
        
        vid = _insert_video(aid, "vid-series", "Series Test")
        
        # Add views on different days
        _insert_view(vid, "1.1.1.1", created_at=now)
        _insert_view(vid, "1.1.1.2", created_at=now)
        _insert_view(vid, "1.1.1.3", created_at=now - 86400)
        
        response = client.get("/api/dashboard/analytics?days=7")
        data = response.get_json()
        
        assert "series" in data
        assert "views" in data["series"]
        assert len(data["series"]["views"]) == 7  # 7 days

    def test_analytics_api_labels_match_series(self, client):
        """Analytics labels should match series length."""
        aid = _insert_agent("labeltest", "test-key-labels")
        _login(client, "labeltest")
        
        for days in [7, 14, 30, 60, 90]:
            response = client.get("/api/dashboard/analytics?days=" + str(days))
            data = response.get_json()
            
            assert len(data["labels"]) == days
            for key in data["series"]:
                assert len(data["series"][key]) == days


# =============================================================================
# Analytics API Tests - Top Videos
# =============================================================================

class TestAnalyticsApiTopVideos:
    """Test analytics API top videos ranking."""

    @pytest.mark.parametrize("limit", ["0", "-1", "51"])
    def test_analytics_api_top_videos_rejects_out_of_range_limit(self, client, limit):
        """Top videos API should reject limits outside the supported 1..50 range."""
        aid = _insert_agent("toplimit" + limit.replace("-", "neg"), "test-key-top-limit-" + limit)

        response = client.get(f"/analytics/api/top-videos?agent_id={aid}&limit={limit}")

        assert response.status_code == 400
        assert "limit" in response.get_json()["error"]

    def test_analytics_api_top_videos_rejects_non_integer_limit(self, client):
        """Top videos API should reject malformed limit values."""
        aid = _insert_agent("toplimitbad", "test-key-top-limit-bad")

        response = client.get(f"/analytics/api/top-videos?agent_id={aid}&limit=abc")

        assert response.status_code == 400
        assert "limit" in response.get_json()["error"]

    @pytest.mark.parametrize("limit", ["1", "50"])
    def test_analytics_api_top_videos_accepts_boundary_limits(self, client, limit):
        """Top videos API should accept the documented 1..50 boundary values."""
        aid = _insert_agent("toplimitvalid" + limit, "test-key-top-limit-valid-" + limit)

        response = client.get(f"/analytics/api/top-videos?agent_id={aid}&limit={limit}")

        assert response.status_code == 200
        assert response.get_json()["videos"] == []

    def test_analytics_api_top_videos_by_views(self, client):
        """Top videos should be ranked by views."""
        aid = _insert_agent("topuser", "test-key-top")
        _login(client, "topuser")
        
        # Create videos with different view counts
        vid1 = _insert_video(aid, "vid-top-1", "Low Views")
        vid2 = _insert_video(aid, "vid-top-2", "High Views")
        vid3 = _insert_video(aid, "vid-top-3", "Medium Views")
        
        for i in range(10):
            _insert_view(vid1, "3.3.3." + str(i))
        for i in range(100):
            _insert_view(vid2, "4.4.4." + str(i))
        for i in range(50):
            _insert_view(vid3, "5.5.5." + str(i))
        
        response = client.get("/api/dashboard/analytics?days=30")
        data = response.get_json()
        
        top_videos = data["top_videos"]
        assert len(top_videos) == 3
        assert top_videos[0]["video_id"] == "vid-top-2"  # Highest views
        assert top_videos[1]["video_id"] == "vid-top-3"  # Medium views
        assert top_videos[2]["video_id"] == "vid-top-1"  # Lowest views

    def test_analytics_api_top_videos_includes_thumbnail(self, client):
        """Top videos should include thumbnail field."""
        aid = _insert_agent("thumbuser", "test-key-thumb")
        _login(client, "thumbuser")
        
        vid = _insert_video(aid, "vid-thumb", "Thumbnail Test")
        _insert_view(vid, "6.6.6.6")
        
        response = client.get("/api/dashboard/analytics?days=30")
        data = response.get_json()
        
        assert "thumbnail" in data["top_videos"][0]

    def test_analytics_api_top_videos_trend_calculation(self, client):
        """Top videos should include trend calculation."""
        now = time.time()
        aid = _insert_agent("trenduser", "test-key-trend")
        _login(client, "trenduser")
        
        vid = _insert_video(aid, "vid-trend", "Trend Test", created_at=now - 30 * 86400)
        
        # Add more recent views than prior views
        for i in range(5):
            _insert_view(vid, "7.7.7." + str(i), created_at=now - 40 * 86400)  # Prior period
        for i in range(10):
            _insert_view(vid, "8.8.8." + str(i), created_at=now)  # Recent period
        
        response = client.get("/api/dashboard/analytics?days=30")
        data = response.get_json()
        
        assert "trend" in data["top_videos"][0]
        assert data["top_videos"][0]["trend"] > 0  # Positive trend


# =============================================================================
# Analytics API Tests - Period Selection
# =============================================================================

class TestAnalyticsApiPeriod:
    """Test analytics API period selection."""

    def test_analytics_api_period_bounds(self, client):
        """Period should be bounded between 7 and 90 days."""
        aid = _insert_agent("perioduser", "test-key-period")
        _login(client, "perioduser")
        
        # Test minimum bound
        response = client.get("/api/dashboard/analytics?days=1")
        data = response.get_json()
        assert len(data["labels"]) >= 7
        
        # Test maximum bound
        response = client.get("/api/dashboard/analytics?days=200")
        data = response.get_json()
        assert len(data["labels"]) <= 90

    def test_analytics_api_default_period(self, client):
        """Default period should be 30 days."""
        aid = _insert_agent("defaultuser", "test-key-default")
        _login(client, "defaultuser")
        
        response = client.get("/api/dashboard/analytics")
        data = response.get_json()
        
        assert len(data["labels"]) == 30


# =============================================================================
# Analytics Dashboard Integration Tests
# =============================================================================

class TestAnalyticsDashboardIntegration:
    """Integration tests for the full analytics dashboard."""

    def test_full_analytics_flow(self, client):
        """Test complete analytics flow with realistic data."""
        now = time.time()
        aid = _insert_agent("fulluser", "test-key-full")
        _login(client, "fulluser")
        
        # Create multiple videos
        videos = []
        for i in range(3):
            vid = _insert_video(aid, "vid-full-" + str(i), "Full Test Video " + str(i))
            videos.append(vid)
        
        # Add views across videos
        for i, vid in enumerate(videos):
            for j in range((i + 1) * 20):
                _insert_view(vid, "9.9." + str(i) + "." + str(j), created_at=now - j * 3600)
        
        # Test analytics page loads
        response = client.get("/analytics")
        assert response.status_code == 200
        
        # Test analytics API returns complete data
        response = client.get("/api/dashboard/analytics?days=30")
        data = response.get_json()
        
        assert data["totals"]["videos"] == 3
        assert data["totals"]["views"] > 0
        assert len(data["top_videos"]) == 3
        assert "series" in data
        assert "labels" in data
