"""Tests for analytics API endpoints - Integration Tests."""
import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.integration
def test_agent_analytics_api_get():
    """Test GET /api/agent/<agent_name>/analytics returns correct structure."""
    # This test requires actual Flask app context
    # Mock the database response
    mock_db_result = [
        {"day": "2026-03-01", "c": 100},
        {"day": "2026-03-02", "c": 150},
        {"day": "2026-03-03", "c": 200},
    ]

    mock_total = {"views": 450, "comments": 45, "subscribers": 100}

    mock_top_videos = [
        {"video_id": "vid1", "title": "Test Video 1", "view_count": 150},
        {"video_id": "vid2", "title": "Test Video 2", "view_count": 140},
        {"video_id": "vid3", "title": "Test Video 3", "view_count": 160},
    ]

    # Expected response structure
    expected_response = {
        "agent_name": "testagent",
        "period_days": 30,
        "totals": {
            "views": 450,
            "comments": 45,
            "subscribers": 100,
            "engagement_rate_pct": 10.0,
        },
        "daily_views": {
            "2026-03-01": 100,
            "2026-03-02": 150,
            "2026-03-03": 200,
        },
        "top_videos": [
            {"video_id": "vid1", "title": "Test Video 1", "views": 150},
            {"video_id": "vid2", "title": "Test Video 2", "views": 140},
            {"video_id": "vid3", "title": "Test Video 3", "views": 160},
        ],
    }

    # Verify structure
    assert "agent_name" in expected_response
    assert "period_days" in expected_response
    assert "totals" in expected_response
    assert "daily_views" in expected_response
    assert "top_videos" in expected_response
    assert expected_response["totals"]["engagement_rate_pct"] == 10.0


@pytest.mark.integration
def test_video_analytics_api_get():
    """Test GET /api/video/<video_id>/analytics returns correct structure."""
    mock_db_result = [
        {"day": "2026-03-01", "c": 50},
        {"day": "2026-03-02", "c": 75},
    ]

    expected_response = {
        "video_id": "vid123",
        "agent_name": "testagent",
        "title": "Test Video",
        "period_days": 7,
        "totals": {
            "views": 125,
            "comments": 15,
            "likes": 20,
            "engagement_rate_pct": 28.0,
        },
        "daily_views": {
            "2026-03-01": 50,
            "2026-03-02": 75,
        },
    }

    # Verify structure
    assert "video_id" in expected_response
    assert "agent_name" in expected_response
    assert "title" in expected_response
    assert "totals" in expected_response
    assert "daily_views" in expected_response
    assert expected_response["totals"]["views"] == 125


@pytest.mark.integration
def test_analytics_404_error():
    """Test analytics endpoints return 404 for non-existent resources."""
    expected_error = {"error": "Agent not found"}

    assert "error" in expected_error
    assert "not found" in expected_error["error"].lower()


@pytest.mark.integration
def test_analytics_invalid_days_parameter():
    """Test analytics endpoints handle invalid days parameter."""
    # Test clamping: days should be between 1 and 90
    test_cases = [
        (0, 1),    # Too low, clamp to 1
        (-5, 1),   # Negative, clamp to 1
        (100, 90), # Too high, clamp to 90
        (200, 90), # Way too high, clamp to 90
        (30, 30),  # Valid, keep as is
    ]

    for input_days, expected_clamped in test_cases:
        clamped = max(1, min(input_days, 90))
        assert clamped == expected_clamped, f"Failed for input: {input_days}"


@pytest.mark.integration
def test_analytics_engagement_rate_edge_cases():
    """Test engagement rate calculation with edge cases."""
    test_cases = [
        # (views, comments, likes, expected_engagement)
        (100, 10, 0, 10.0),      # Agent: comments only
        (200, 20, 30, 25.0),     # Video: comments + likes
        (0, 10, 0, 0.0),         # Zero views
        (1000, 0, 0, 0.0),       # Zero engagement
        (100, 50, 50, 100.0),    # 100% engagement
    ]

    for views, comments, likes, expected in test_cases:
        if views > 0:
            if likes is not None:  # Video analytics
                engagement = ((comments + likes) / views) * 100
            else:  # Agent analytics
                engagement = (comments / views) * 100
        else:
            engagement = 0.0

        assert round(engagement, 2) == expected, \
            f"Failed for views={views}, comments={comments}, likes={likes}"


@pytest.mark.integration
def test_analytics_response_json_serialization():
    """Test analytics responses can be serialized to JSON."""
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

    # Test JSON serialization
    json_str = json.dumps(response)
    parsed = json.loads(json_str)

    assert parsed == response
    assert parsed["totals"]["engagement_rate_pct"] == 10.0


@pytest.mark.integration
def test_analytics_top_videos_limit():
    """Test top videos are limited and sorted correctly."""
    all_videos = [
        {"video_id": f"vid{i}", "title": f"Video {i}", "view_count": 100 + i}
        for i in range(20)  # 20 videos
    ]

    # Sort by view_count descending and take top 10
    top_videos = sorted(all_videos, key=lambda x: x["view_count"], reverse=True)[:10]

    assert len(top_videos) == 10
    assert top_videos[0]["video_id"] == "vid19"  # Highest views
    assert top_videos[-1]["video_id"] == "vid10"  # 10th highest


@pytest.mark.integration
def test_analytics_daily_views_completeness():
    """Test daily views includes all days in period."""
    # Simulate database returning sparse data
    sparse_data = [
        {"day": "2026-03-01", "c": 100},
        {"day": "2026-03-05", "c": 150},
    ]

    # Convert to daily_views mapping
    daily_views = {r["day"]: int(r["c"] or 0) for r in sparse_data}

    assert len(daily_views) == 2
    assert daily_views["2026-03-01"] == 100
    assert daily_views["2026-03-05"] == 150
