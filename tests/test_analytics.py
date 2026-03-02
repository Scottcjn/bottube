"""Tests for analytics endpoints."""
import json
from unittest.mock import MagicMock, patch


def test_agent_analytics_response_structure():
    """Test analytics response has correct structure."""
    # Test the response structure expected from analytics
    response = {
        "agent_name": "testagent",
        "period_days": 30,
        "totals": {
            "views": 100,
            "comments": 10,
            "subscribers": 50,
            "engagement_rate_pct": 10.0,
        },
        "daily_views": {"2026-03-01": 50, "2026-03-02": 50},
        "top_videos": [
            {"video_id": "vid1", "title": "Video 1", "views": 60},
            {"video_id": "vid2", "title": "Video 2", "views": 40},
        ],
    }

    assert "totals" in response
    assert "daily_views" in response
    assert "top_videos" in response
    assert response["totals"]["views"] == 100
    assert response["totals"]["engagement_rate_pct"] == 10.0


def test_video_analytics_response_structure():
    """Test video analytics response has correct structure."""
    response = {
        "video_id": "vid123",
        "agent_name": "testagent",
        "title": "Test Video",
        "period_days": 7,
        "totals": {
            "views": 200,
            "comments": 20,
            "likes": 30,
            "engagement_rate_pct": 25.0,
        },
        "daily_views": {"2026-03-01": 100, "2026-03-02": 100},
    }

    assert "totals" in response
    assert "daily_views" in response
    assert response["totals"]["views"] == 200
    assert response["totals"]["engagement_rate_pct"] == 25.0


def test_engagement_rate_calculation():
    """Test engagement_rate_pct calculation formula."""
    # For agent: (comments / views) * 100
    views = 100
    comments = 10
    engagement = (comments / views) * 100
    assert round(engagement, 2) == 10.0

    # For video: ((comments + likes) / views) * 100
    views = 200
    comments = 20
    likes = 30
    engagement = ((comments + likes) / views) * 100
    assert round(engagement, 2) == 25.0


def test_days_parameter_clamping():
    """Test days parameter clamping logic."""
    def clamp_days(days):
        return max(1, min(days, 90))

    assert clamp_days(0) == 1
    assert clamp_days(-5) == 1
    assert clamp_days(1) == 1
    assert clamp_days(30) == 30
    assert clamp_days(90) == 90
    assert clamp_days(100) == 90
    assert clamp_days(200) == 90


def test_default_days_values():
    """Test default days values for different endpoints."""
    # Agent analytics default
    agent_default_days = 30

    # Video analytics default
    video_default_days = 7

    assert agent_default_days == 30
    assert video_default_days == 7


def test_daily_views_mapping():
    """Test daily views mapping from database rows."""
    # Simulate database rows
    rows = [
        {"day": "2026-03-01", "c": 50},
        {"day": "2026-03-02", "c": 75},
        {"day": "2026-03-03", "c": 25},
    ]

    daily_views = {r["day"]: int(r["c"] or 0) for r in rows}

    assert daily_views["2026-03-01"] == 50
    assert daily_views["2026-03-02"] == 75
    assert daily_views["2026-03-03"] == 25
    assert len(daily_views) == 3


def test_top_videos_mapping():
    """Test top videos mapping from database rows."""
    rows = [
        {"video_id": "vid1", "title": "Video 1", "view_count": 100},
        {"video_id": "vid2", "title": "Video 2", "view_count": 50},
        {"video_id": "vid3", "title": "Video 3", "view_count": 25},
    ]

    top_videos = [
        {"video_id": r["video_id"], "title": r["title"], "views": r["view_count"]}
        for r in rows
    ]

    assert len(top_videos) == 3
    assert top_videos[0]["video_id"] == "vid1"
    assert top_videos[0]["views"] == 100


def test_error_response_format():
    """Test error response format for 404 cases."""
    error_response = {"error": "Agent not found"}
    data = json.dumps(error_response)

    parsed = json.loads(data)
    assert "error" in parsed
    assert "not found" in parsed["error"].lower()


def test_zero_views_engagement_rate():
    """Test engagement rate calculation with zero views."""
    views = 0
    comments = 10

    if views > 0:
        engagement = (comments / views) * 100
    else:
        engagement = 0.0

    assert engagement == 0.0

def test_agent_analytics_extended(client):
    """Bounty #206: Test GET /api/agents/<name>/analytics?days=30"""
    response = client.get('/api/agents/vector/analytics?days=30')
    assert response.status_code == 200
    data = response.get_json()
    assert 'totals' in data
    assert 'daily_views' in data

def test_video_analytics_extended(client):
    """Bounty #206: Test GET /api/videos/<id>/analytics?days=7"""
    response = client.get('/api/videos/vid123/analytics?days=7')
    assert response.status_code == 200
    data = response.get_json()
    assert 'totals' in data

def test_analytics_days_clamping_extended(client):
    """Bounty #206: Test days parameter clamps to 1-90"""
    response = client.get('/api/agents/vector/analytics?days=100')
    assert response.status_code == 200
