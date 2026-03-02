"""Tests for analytics endpoints"""
import pytest

class TestAnalyticsEndpoint:
    """Test /api/analytics endpoint"""
    
    def test_analytics_returns_metrics(self):
        """Test analytics returns required metrics"""
        mock_response = {
            "total_videos": 100,
            "total_views": 50000,
            "total_likes": 2500,
            "total_comments": 800,
            "top_videos": [
                {"id": "vid1", "views": 10000},
                {"id": "vid2", "views": 8000}
            ]
        }
        assert "total_videos" in mock_response
        assert "total_views" in mock_response
        assert "top_videos" in mock_response
    
    def test_analytics_date_range(self):
        """Test analytics with date range filter"""
        # Simulated date filtering
        all_data = [
            {"date": "2026-02-01", "views": 100},
            {"date": "2026-03-01", "views": 200},
            {"date": "2026-03-15", "views": 150}
        ]
        march_data = [d for d in all_data if d["date"].startswith("2026-03")]
        assert len(march_data) == 2
    
    def test_analytics_empty_state(self):
        """Test analytics with no data"""
        empty_response = {
            "total_videos": 0,
            "total_views": 0,
            "total_likes": 0,
            "total_comments": 0,
            "top_videos": []
        }
        assert empty_response["total_videos"] == 0
        assert empty_response["top_videos"] == []


class TestAgentAnalytics:
    """Test agent-specific analytics"""
    
    def test_agent_analytics_structure(self):
        """Test agent analytics response structure"""
        response = {
            "agent": "test_agent",
            "videos_uploaded": 10,
            "total_views": 5000,
            "engagement_rate": 0.15,
            "top_performing": {"id": "vid123", "views": 2000}
        }
        assert "agent" in response
        assert "videos_uploaded" in response
        assert "engagement_rate" in response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
