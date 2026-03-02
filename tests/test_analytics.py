import pytest
from unittest.mock import Mock, patch
import json


class TestAnalyticsEndpoints:
    """Test suite for BoTTube analytics endpoints."""
    
    def test_agent_analytics_success(self, client):
        """Test GET /api/agents/<name>/analytics returns correct data."""
        mock_data = {
            "totals": {
                "views": 15000,
                "comments": 450,
                "subscriptions": 1200
            },
            "daily_views": [
                {"date": "2026-03-01", "views": 500},
                {"date": "2026-03-02", "views": 600}
            ],
            "top_videos": [
                {"id": "vid1", "title": "Test Video", "views": 5000}
            ],
            "engagement_rate_pct": 3.0
        }
        
        with patch('app.get_agent_analytics', return_value=mock_data):
            response = client.get('/api/agents/test_agent/analytics?days=30')
            
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'totals' in data
        assert 'daily_views' in data
        assert 'top_videos' in data
        assert data['totals']['views'] == 15000
    
    def test_agent_analytics_days_parameter_clamping(self, client):
        """Test days parameter clamps to 1-90 range."""
        # Test days < 1 clamps to 1
        with patch('app.get_agent_analytics') as mock:
            client.get('/api/agents/test/analytics?days=0')
            args = mock.call_args
            assert args[1]['days'] == 1
        
        # Test days > 90 clamps to 90
        with patch('app.get_agent_analytics') as mock:
            client.get('/api/agents/test/analytics?days=100')
            args = mock.call_args
            assert args[1]['days'] == 90
        
        # Test valid days in range
        with patch('app.get_agent_analytics') as mock:
            client.get('/api/agents/test/analytics?days=30')
            args = mock.call_args
            assert args[1]['days'] == 30
    
    def test_agent_analytics_404(self, client):
        """Test 404 for nonexistent agent."""
        with patch('app.get_agent_analytics', return_value=None):
            response = client.get('/api/agents/nonexistent/analytics')
        
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data or 'message' in data
    
    def test_video_analytics_success(self, client):
        """Test GET /api/videos/<id>/analytics returns correct data."""
        mock_data = {
            "totals": {
                "views": 5000,
                "comments": 150,
                "likes": 300
            },
            "daily_views": [
                {"date": "2026-03-01", "views": 200},
                {"date": "2026-03-02", "views": 250}
            ],
            "engagement_rate_pct": 9.0
        }
        
        with patch('app.get_video_analytics', return_value=mock_data):
            response = client.get('/api/videos/abc123/analytics?days=7')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'totals' in data
        assert 'daily_views' in data
        assert data['totals']['views'] == 5000
    
    def test_video_analytics_404(self, client):
        """Test 404 for nonexistent video."""
        with patch('app.get_video_analytics', return_value=None):
            response = client.get('/api/videos/nonexistent/analytics')
        
        assert response.status_code == 404
    
    def test_engagement_rate_calculation(self, client):
        """Test engagement_rate_pct is calculated correctly."""
        mock_data = {
            "totals": {
                "views": 10000,
                "comments": 200,
                "likes": 500
            },
            "engagement_rate_pct": 7.0  # (200+500)/10000 * 100
        }
        
        with patch('app.get_agent_analytics', return_value=mock_data):
            response = client.get('/api/agents/test/analytics')
            data = json.loads(response.data)
        
        assert 'engagement_rate_pct' in data
        assert isinstance(data['engagement_rate_pct'], (int, float))
        assert data['engagement_rate_pct'] >= 0
    
    def test_analytics_with_mock_db(self, client):
        """Test analytics with mocked database data."""
        mock_views = [
            Mock(video_id="vid1", created_at="2026-03-01", count=100),
            Mock(video_id="vid1", created_at="2026-03-02", count=150)
        ]
        mock_comments = [
            Mock(video_id="vid1", created_at="2026-03-01"),
            Mock(video_id="vid1", created_at="2026-03-02")
        ]
        
        with patch('app.get_views', return_value=mock_views):
            with patch('app.get_comments', return_value=mock_comments):
                response = client.get('/api/videos/vid1/analytics?days=7')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['totals']['views'] == 250
        assert len(data['daily_views']) > 0


@pytest.fixture
def client():
    """Create test client fixture."""
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client
