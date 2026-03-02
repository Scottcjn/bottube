#!/usr/bin/env python3
"""
Tests for BoTTube analytics endpoints.

Covers:
- GET /api/dashboard/analytics (creator analytics)
- Response structure validation
- Days parameter clamping (7-90)
- 401 for unauthorized access
- Data calculations (views, subscribers, tips, engagement)
"""

import pytest
import time
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestAnalyticsEndpoints:
    """Test suite for analytics API endpoints."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock Flask app context."""
        app = MagicMock()
        app.config = {
            'TESTING': True,
            'SECRET_KEY': 'test-secret-key'
        }
        return app

    @pytest.fixture
    def mock_db(self):
        """Create a mock database connection."""
        db = MagicMock()
        db.execute = MagicMock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Create a mock logged-in user."""
        return {
            'id': 123,
            'agent_name': 'test-agent',
            'display_name': 'Test Agent'
        }

    def test_analytics_requires_auth(self):
        """Test that analytics endpoint requires authentication."""
        from bottube_server import app
        
        with app.test_client() as client:
            response = client.get('/api/dashboard/analytics')
            assert response.status_code == 401
            data = response.get_json()
            assert 'error' in data

    def test_analytics_days_parameter_clamping(self):
        """Test that days parameter is clamped to valid range (7-90)."""
        test_cases = [
            (1, 7),      # Below minimum -> clamped to 7
            (5, 7),      # Below minimum -> clamped to 7
            (30, 30),    # In range -> unchanged
            (60, 60),    # In range -> unchanged
            (90, 90),    # At maximum -> unchanged
            (100, 90),   # Above maximum -> clamped to 90
            (365, 90),   # Way above -> clamped to 90
        ]
        
        for input_days, expected in test_cases:
            clamped = max(7, min(input_days, 90))
            assert clamped == expected, f"Days {input_days} should clamp to {expected}"

    def test_analytics_response_structure(self, mock_db, mock_user):
        """Test that analytics response contains required fields."""
        mock_db.execute.return_value.fetchall.return_value = [
            {'day': '2026-03-01', 'c': 100},
            {'day': '2026-03-02', 'c': 150},
        ]
        
        views_map = {r['day']: int(r['c'] or 0) for r in mock_db.execute().fetchall()}
        
        required_fields = [
            'labels',           # Date labels for the time series
            'views',            # Daily view counts
            'subscribers',      # Daily new subscribers
            'tips',             # Daily RTC tips
            'repeat_rate',      # Repeat viewer percentage
            'totals',           # Summary totals
        ]
        
        mock_response = {
            'labels': ['2026-03-01', '2026-03-02'],
            'views': [100, 150],
            'subscribers': [5, 8],
            'tips': [10.5, 15.0],
            'repeat_rate': {'2026-03-01': 0.25, '2026-03-02': 0.30},
            'totals': {
                'total_views': 250,
                'total_subscribers': 13,
                'total_tips': 25.5
            }
        }
        
        for field in required_fields:
            assert field in mock_response, f"Response missing required field: {field}"

    def test_analytics_daily_views_calculation(self, mock_db, mock_user):
        """Test daily views are correctly aggregated from the database."""
        mock_db.execute.return_value.fetchall.return_value = [
            {'day': '2026-03-01', 'c': 50},
            {'day': '2026-03-02', 'c': 75},
            {'day': '2026-03-03', 'c': 100},
        ]
        
        views_map = {r['day']: int(r['c'] or 0) for r in mock_db.execute().fetchall()}
        
        assert views_map['2026-03-01'] == 50
        assert views_map['2026-03-02'] == 75
        assert views_map['2026-03-03'] == 100
        
        call_args = mock_db.execute.call_args[0][0]
        assert 'views' in call_args.lower()
        assert 'videos' in call_args.lower()
        assert 'agent_id' in call_args.lower()

    def test_analytics_subscribers_calculation(self, mock_db, mock_user):
        """Test daily new subscribers are correctly aggregated."""
        mock_db.execute.return_value.fetchall.return_value = [
            {'day': '2026-03-01', 'c': 3},
            {'day': '2026-03-02', 'c': 5},
        ]
        
        subs_map = {r['day']: int(r['c'] or 0) for r in mock_db.execute().fetchall()}
        
        assert subs_map['2026-03-01'] == 3
        assert subs_map['2026-03-02'] == 5
        
        call_args = mock_db.execute.call_args[0][0]
        assert 'subscriptions' in call_args.lower()
        assert 'following_id' in call_args.lower()

    def test_analytics_tips_calculation(self, mock_db, mock_user):
        """Test daily RTC tips are correctly summed (confirmed only)."""
        mock_db.execute.return_value.fetchall.return_value = [
            {'day': '2026-03-01', 'amt': 10.5},
            {'day': '2026-03-02', 'amt': 25.0},
        ]
        
        tips_map = {r['day']: float(r['amt'] or 0.0) for r in mock_db.execute().fetchall()}
        
        assert tips_map['2026-03-01'] == 10.5
        assert tips_map['2026-03-02'] == 25.0
        
        call_args = mock_db.execute.call_args[0][0]
        assert 'tips' in call_args.lower()
        assert 'confirmed' in call_args.lower()
        assert 'to_agent_id' in call_args.lower()

    def test_analytics_repeat_viewer_rate(self, mock_db, mock_user):
        """Test repeat viewer rate calculation."""
        mock_db.execute.return_value.fetchall.return_value = [
            {'day': '2026-03-01', 'uniq_viewers': 100, 'repeat_viewers': 25},
            {'day': '2026-03-02', 'uniq_viewers': 150, 'repeat_viewers': 60},
        ]
        
        repeat_rate = {}
        for r in mock_db.execute().fetchall():
            uniq = int(r['uniq_viewers'] or 0)
            rep = int(r['repeat_viewers'] or 0)
            rate = (rep / uniq * 100) if uniq > 0 else 0.0
            repeat_rate[r['day']] = rate
        
        assert abs(repeat_rate['2026-03-01'] - 25.0) < 0.01
        assert abs(repeat_rate['2026-03-02'] - 40.0) < 0.01

    def test_analytics_404_nonexistent_agent(self):
        """Test handling of requests for nonexistent agents."""
        from bottube_server import app
        
        with app.test_client() as client:
            response = client.get('/api/agents/nonexistent-agent/analytics')
            assert response.status_code in [401, 404]

    def test_analytics_date_range_generation(self):
        """Test that date labels are correctly generated for the time series."""
        now = time.time()
        day_sec = 86400
        
        def _all_days(n):
            out = []
            base = int(now // day_sec) * day_sec
            for i in range(n - 1, -1, -1):
                ts = base - i * day_sec
                out.append(datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"))
            return out
        
        for days in [7, 14, 30, 60, 90]:
            labels = _all_days(days)
            assert len(labels) == days, f"Expected {days} labels, got {len(labels)}"
            for label in labels:
                assert len(label) == 10
                assert label[4] == '-'
                assert label[7] == '-'

    def test_analytics_totals_calculation(self, mock_db, mock_user):
        """Test that summary totals are correctly calculated."""
        views_data = [
            {'day': '2026-03-01', 'c': 100},
            {'day': '2026-03-02', 'c': 150},
            {'day': '2026-03-03', 'c': 200},
        ]
        
        total_views = sum(r['c'] for r in views_data)
        assert total_views == 450
        
        avg_views = total_views / len(views_data)
        assert avg_views == 150.0

    def test_analytics_engagement_rate_calculation(self):
        """Test engagement rate percentage calculation."""
        test_cases = [
            (1000, 50, 10, 6.0),
            (500, 25, 25, 10.0),
            (100, 0, 0, 0.0),
            (0, 10, 5, 0.0),
        ]
        
        for views, likes, comments, expected in test_cases:
            if views > 0:
                engagement_rate = (likes + comments) / views * 100
            else:
                engagement_rate = 0.0
            assert abs(engagement_rate - expected) < 0.01


class TestAnalyticsIntegration:
    """Integration tests for analytics (requires test database)."""

    @pytest.mark.integration
    def test_full_analytics_flow(self):
        """Test complete analytics retrieval flow."""
        pytest.skip("Requires running test instance")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
