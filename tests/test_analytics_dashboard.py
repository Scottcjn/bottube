"""
Tests for Creator Analytics Dashboard (issue #423).
Tests cover:
- Analytics page access control
- Analytics API endpoint with various data scenarios
- Empty states for new users
- Core metrics calculation (views, engagement, top videos, trend)
"""

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_analytics.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_analytics.db")

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
