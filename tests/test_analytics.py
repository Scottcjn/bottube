import pytest
from unittest.mock import patch, MagicMock
from app import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@patch('services.analytics.get_agent_analytics')
def test_agent_analytics_success(mock_get_analytics, client):
    """Test successful agent analytics response structure"""
    mock_data = {
        'totals': {'views': 100, 'comments': 10, 'subscriptions': 5},
        'daily_views': [{'date': '2023-01-01', 'views': 10}],
        'top_videos': [{'id': 'vid1', 'title': 'Video 1', 'views': 50}]
    }
    mock_get_analytics.return_value = mock_data

    response = client.get('/api/agents/test_agent/analytics?days=30')
    assert response.status_code == 200
    data = response.json
    
    assert 'totals' in data
    assert 'daily_views' in data
    assert 'top_videos' in data
    assert data['totals']['views'] == 100
    assert len(data['daily_views']) == 1
    assert len(data['top_videos']) == 1

@patch('services.analytics.get_agent_analytics')
def test_agent_analytics_days_clamping(mock_get_analytics, client):
    """Test days parameter clamping (1-90)"""
    # Test min clamping (days=0 -> 1)
    response = client.get('/api/agents/test_agent/analytics?days=0')
    assert response.status_code == 200
    mock_get_analytics.assert_called_with('test_agent', 1)

    # Test max clamping (days=100 -> 90)
    response = client.get('/api/agents/test_agent/analytics?days=100')
    assert response.status_code == 200
    mock_get_analytics.assert_called_with('test_agent', 90)

@patch('services.analytics.get_agent_analytics')
def test_agent_analytics_not_found(mock_get_analytics, client):
    """Test 404 for non-existent agent"""
    mock_get_analytics.return_value = None
    
    response = client.get('/api/agents/non_existent/analytics?days=30')
    assert response.status_code == 404
    assert 'error' in response.json

@patch('services.analytics.get_agent_analytics')
def test_agent_engagement_rate_calculation(mock_get_analytics, client):
    """Test engagement_rate_pct calculation"""
    mock_data = {
        'totals': {'views': 200, 'comments': 30, 'subscriptions': 10},
        'daily_views': [],
        'top_videos': []
    }
    mock_get_analytics.return_value = mock_data

    response = client.get('/api/agents/test_agent/analytics?days=30')
    data = response.json
    
    # engagement_rate_pct = (comments + subscriptions) / views * 100
    expected_rate = (30 + 10) / 200 * 100
    assert data['totals']['engagement_rate_pct'] == pytest.approx(expected_rate)

@patch('services.analytics.get_video_analytics')
def test_video_analytics_success(mock_get_analytics, client):
    """Test successful video analytics response structure"""
    mock_data = {
        'totals': {'views': 500, 'comments': 25, 'subscriptions': 15},
        'daily_views': [{'date': '2023-01-01', 'views': 50}],
        'top_videos': []
    }
    mock_get_analytics.return_value = mock_data

    response = client.get('/api/videos/video123/analytics?days=7')
    assert response.status_code == 200
    data = response.json
    
    assert 'totals' in data
    assert 'daily_views' in data
    assert 'top_videos' in data
    assert data['totals']['views'] == 500
    assert len(data['daily_views']) == 1

@patch('services.analytics.get_video_analytics')
def test_video_analytics_days_clamping(mock_get_analytics, client):
    """Test days parameter clamping for video endpoint"""
    # Test min clamping
    response = client.get('/api/videos/video123/analytics?days=-1')
    assert response.status_code == 200
    mock_get_analytics.assert_called_with('video123', 1)

    # Test max clamping
    response = client.get('/api/videos/video123/analytics?days=100')
    assert response.status_code == 200
    mock_get_analytics.assert_called_with('video123', 90)

@patch('services.analytics.get_video_analytics')
def test_video_analytics_not_found(mock_get_analytics, client):
    """Test 404 for non-existent video"""
    mock_get_analytics.return_value = None
    
    response = client.get('/api/videos/non_existent/analytics?days=7')
    assert response.status_code == 404
    assert 'error' in response.json

@patch('services.analytics.get_video_analytics')
def test_video_engagement_rate_calculation(mock_get_analytics, client):
    """Test engagement_rate_pct calculation for video"""
    mock_data = {
        'totals': {'views': 1000, 'comments': 100, 'subscriptions': 50},
        'daily_views': [],
        'top_videos': []
    }
    mock_get_analytics.return_value = mock_data

    response = client.get('/api/videos/video123/analytics?days=7')
    data = response.json
    
    expected_rate = (100 + 50) / 1000 * 100
    assert data['totals']['engagement_rate_pct'] == pytest.approx(expected_rate)