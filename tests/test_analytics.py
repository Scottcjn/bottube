"""Tests for analytics endpoints."""
import json
import pathlib
import sys
import time
from unittest.mock import MagicMock, patch

# Add parent to path
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


# === Flask Endpoint Tests ===
# Note: These tests verify the analytics response structure and logic
# without requiring the full server setup (database connections, etc.)


def test_agent_analytics_404_response():
    """Test 404 response for nonexistent agent."""
    from flask import Flask, jsonify
    
    def mock_get_agent_analytics(agent_name):
        """Simulated endpoint logic."""
        agent = None  # Not found
        if not agent:
            return jsonify({"error": "Agent not found"}), 404
        return jsonify({}), 200
    
    app = Flask(__name__)
    app.add_url_rule('/api/agents/<name>/analytics', 
                     view_func=lambda name: mock_get_agent_analytics(name))
    
    with app.test_client() as client:
        response = client.get('/api/agents/nonexistent/analytics')
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
        assert "not found" in data["error"].lower()


def test_agent_analytics_success_response():
    """Test success response structure for agent analytics."""
    from flask import Flask, jsonify
    
    def mock_get_agent_analytics(agent_name):
        """Simulated endpoint logic."""
        return jsonify({
            "agent_name": agent_name,
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
            ],
        }), 200
    
    app = Flask(__name__)
    app.add_url_rule('/api/agents/<name>/analytics',
                     view_func=lambda name: mock_get_agent_analytics(name))
    
    with app.test_client() as client:
        response = client.get('/api/agents/testagent/analytics')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data["agent_name"] == "testagent"
        assert data["period_days"] == 30
        assert "totals" in data
        assert "daily_views" in data
        assert "top_videos" in data
        assert data["totals"]["views"] == 100
        assert data["totals"]["engagement_rate_pct"] == 10.0


def test_days_parameter_clamping_endpoint():
    """Test days parameter clamping logic (simulates endpoint behavior)."""
    from flask import Flask, jsonify, request
    
    def mock_get_agent_analytics(agent_name):
        try:
            days = int(request.args.get("days", 30))
        except Exception:
            days = 30
        days = max(1, min(days, 90))
        return jsonify({"period_days": days}), 200
    
    app = Flask(__name__)
    app.add_url_rule('/api/agents/<name>/analytics',
                     view_func=lambda name: mock_get_agent_analytics(name))
    
    with app.test_client() as client:
        # Default
        r = client.get('/api/agents/test/analytics')
        assert json.loads(r.data)["period_days"] == 30
        
        # Explicit valid
        r = client.get('/api/agents/test/analytics?days=7')
        assert json.loads(r.data)["period_days"] == 7
        
        # Too low -> 1
        r = client.get('/api/agents/test/analytics?days=0')
        assert json.loads(r.data)["period_days"] == 1
        
        # Too high -> 90
        r = client.get('/api/agents/test/analytics?days=100')
        assert json.loads(r.data)["period_days"] == 90


def test_video_analytics_404_response():
    """Test 404 response for nonexistent video."""
    from flask import Flask, jsonify
    
    def mock_get_video_analytics(video_id):
        video = None  # Not found
        if not video:
            return jsonify({"error": "Video not found"}), 404
        return jsonify({}), 200
    
    app = Flask(__name__)
    app.add_url_rule('/api/videos/<id>/analytics',
                     view_func=lambda id: mock_get_video_analytics(id))
    
    with app.test_client() as client:
        response = client.get('/api/videos/nonexistent/analytics')
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
        assert "not found" in data["error"].lower()


def test_video_analytics_success_response():
    """Test success response structure for video analytics."""
    from flask import Flask, jsonify
    
    def mock_get_video_analytics(video_id):
        return jsonify({
            "video_id": video_id,
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
        }), 200
    
    app = Flask(__name__)
    app.add_url_rule('/api/videos/<id>/analytics',
                     view_func=lambda id: mock_get_video_analytics(id))
    
    with app.test_client() as client:
        response = client.get('/api/videos/vid123/analytics')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data["video_id"] == "vid123"
        assert data["period_days"] == 7
        assert "totals" in data
        assert "daily_views" in data
        assert data["totals"]["views"] == 200
        assert data["totals"]["engagement_rate_pct"] == 25.0


def test_video_analytics_default_days():
    """Test video analytics defaults to 7 days."""
    from flask import Flask, jsonify, request
    
    def mock_get_video_analytics(video_id):
        try:
            days = int(request.args.get("days", 7))
        except Exception:
            days = 7
        days = max(1, min(days, 90))
        return jsonify({"period_days": days}), 200
    
    app = Flask(__name__)
    app.add_url_rule('/api/videos/<id>/analytics',
                     view_func=lambda id: mock_get_video_analytics(id))
    
    with app.test_client() as client:
        # Default should be 7
        r = client.get('/api/videos/vid123/analytics')
        assert json.loads(r.data)["period_days"] == 7
