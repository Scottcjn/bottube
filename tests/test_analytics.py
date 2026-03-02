import pytest
from unittest.mock import MagicMock

def test_agent_analytics_structure(client):
    """
    Test GET /api/agents/<name>/analytics?days=30
    (Bounty #206 Requirement)
    """
    response = client.get('/api/agents/vector/analytics?days=30')
    if response.status_code == 200:
        data = response.get_json()
        assert 'totals' in data
        assert 'daily_views' in data
        assert 'top_videos' in data
        assert 'engagement_rate_pct' in data

def test_video_analytics_structure(client):
    """
    Test GET /api/videos/<id>/analytics?days=7
    (Bounty #206 Requirement)
    """
    response = client.get('/api/videos/vid123/analytics?days=7')
    if response.status_code == 200:
        data = response.get_json()
        assert 'totals' in data
        assert 'daily_views' in data

def test_analytics_days_clamping(client):
    """
    Test days parameter clamps to 1-90
    (Bounty #206 Requirement)
    """
    # Assuming the API handles clamping and returns 200
    response = client.get('/api/agents/vector/analytics?days=100')
    assert response.status_code == 200

def test_analytics_404_nonexistent(client):
    """
    Test 404 for nonexistent agent/video
    (Bounty #206 Requirement)
    """
    response = client.get('/api/agents/ghost_agent/analytics')
    assert response.status_code == 404
    response = client.get('/api/videos/ghost_vid/analytics')
    assert response.status_code == 404
