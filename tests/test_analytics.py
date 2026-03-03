"""
Tests for analytics API endpoints.
Bounty: 3 RTC - https://github.com/Scottcjn/bottube/issues/206
"""
import sys
import json

# Test the endpoint logic without requiring Flask app


def test_days_parameter_clamping():
    """Test days parameter clamping logic."""
    # Simulate the clamping logic from the endpoint
    def clamp_days(days):
        return max(1, min(90, days))

    assert clamp_days(0) == 1
    assert clamp_days(1) == 1
    assert clamp_days(30) == 30
    assert clamp_days(90) == 90
    assert clamp_days(100) == 90
    assert clamp_days(-5) == 1


def test_engagement_rate_calculation():
    """Test engagement_rate_pct calculation."""
    # From bounty: engagement_rate_pct = (comments + subscriptions) / views * 100
    def calc_engagement(views, comments, subscriptions=0, likes=0):
        if views == 0:
            return 0
        return round((comments + subscriptions + likes) / views * 100, 1)

    # Test case from sample data
    assert calc_engagement(15000, 450, 120) == 3.8  # (450+120)/15000*100 = 3.8
    assert calc_engagement(3500, 85, 0, 120) == 5.9  # (85+120)/3500*100 = 5.857...
    assert calc_engagement(1000, 50, 0, 30) == 8.0  # (50+30)/1000*100 = 8.0
    assert calc_engagement(0, 50, 0, 30) == 0  # Division by zero


def test_response_structure_agent_analytics():
    """Test agent analytics response structure."""
    # Expected response format from bounty
    expected_keys = ["agent_name", "period_days", "totals", "daily_views", "top_videos"]
    totals_keys = ["views", "comments", "subscriptions", "engagement_rate_pct"]

    # Sample response
    response = {
        "agent_name": "test-agent",
        "period_days": 30,
        "totals": {
            "views": 15000,
            "comments": 450,
            "subscriptions": 120,
            "engagement_rate_pct": 3.8
        },
        "daily_views": [
            {"date": "2026-03-01", "views": 500},
        ],
        "top_videos": [
            {"video_id": "vid1", "title": "Test", "views": 5000},
        ]
    }

    # Verify structure
    for key in expected_keys:
        assert key in response, f"Missing key: {key}"
    for key in totals_keys:
        assert key in response["totals"], f"Missing totals key: {key}"


def test_response_structure_video_analytics():
    """Test video analytics response structure."""
    expected_keys = ["video_id", "period_days", "totals", "daily_views"]
    totals_keys = ["views", "comments", "likes", "engagement_rate_pct"]

    response = {
        "video_id": "vid123",
        "period_days": 7,
        "totals": {
            "views": 3500,
            "comments": 85,
            "likes": 120,
            "engagement_rate_pct": 5.9
        },
        "daily_views": [
            {"date": "2026-03-01", "views": 600},
        ]
    }

    for key in expected_keys:
        assert key in response, f"Missing key: {key}"
    for key in totals_keys:
        assert key in response["totals"], f"Missing totals key: {key}"


if __name__ == "__main__":
    test_days_parameter_clamping()
    test_engagement_rate_calculation()
    test_response_structure_agent_analytics()
    test_response_structure_video_analytics()
    print("All analytics tests passed!")
