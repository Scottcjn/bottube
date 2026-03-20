"""
Tests for TV API endpoints for Roku/Fire TV BoTTube client.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from bottube_server import app, get_db


@pytest.fixture
def client():
    """Test client fixture."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def mock_db():
    """Mock database fixture."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


class TestTVVideoListing:
    """Test TV API video listing endpoints."""

    def test_tv_videos_default(self, client, mock_db):
        """Test default video listing for TV."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchall.return_value = [
            (1, 'Test Video 1', 'test-video-1', 'user1', 1000, 100, 50, 'https://example.com/thumb1.jpg'),
            (2, 'Test Video 2', 'test-video-2', 'user2', 800, 80, 40, 'https://example.com/thumb2.jpg')
        ]

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/videos')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'videos' in data
            assert len(data['videos']) == 2
            assert data['videos'][0]['title'] == 'Test Video 1'
            assert 'thumbnail' in data['videos'][0]

    def test_tv_videos_pagination(self, client, mock_db):
        """Test video listing with pagination."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchall.return_value = []

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/videos?page=2&limit=20')

            assert response.status_code == 200
            mock_cursor.execute.assert_called()
            call_args = mock_cursor.execute.call_args[0][0]
            assert 'LIMIT' in call_args
            assert 'OFFSET' in call_args

    def test_tv_videos_trending(self, client, mock_db):
        """Test trending videos for TV."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchall.return_value = [
            (1, 'Trending Video', 'trending-video', 'user1', 5000, 500, 250, 'thumb.jpg')
        ]

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/videos/trending')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'videos' in data
            mock_cursor.execute.assert_called()
            # Should order by views or engagement
            query = mock_cursor.execute.call_args[0][0].lower()
            assert 'order by' in query

    def test_tv_videos_recent(self, client, mock_db):
        """Test recent videos for TV."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchall.return_value = []

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/videos/recent')

            assert response.status_code == 200
            mock_cursor.execute.assert_called()
            query = mock_cursor.execute.call_args[0][0].lower()
            assert 'order by' in query and 'created_at' in query


class TestTVVideoSearch:
    """Test TV API video search functionality."""

    def test_tv_search_basic(self, client, mock_db):
        """Test basic video search for TV."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchall.return_value = [
            (1, 'Searchable Video', 'searchable-video', 'user1', 100, 10, 5, 'thumb.jpg')
        ]

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/search?q=searchable')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'videos' in data
            assert 'query' in data
            assert data['query'] == 'searchable'

    def test_tv_search_empty_query(self, client):
        """Test search with empty query."""
        response = client.get('/api/tv/search')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_tv_search_no_results(self, client, mock_db):
        """Test search with no results."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchall.return_value = []

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/search?q=nonexistent')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data['videos']) == 0


class TestTVCategoryFiltering:
    """Test TV API category filtering."""

    def test_tv_categories_list(self, client, mock_db):
        """Test getting available categories for TV."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchall.return_value = [
            ('Gaming',), ('Music',), ('Education',), ('Entertainment',)
        ]

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/categories')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'categories' in data
            assert 'Gaming' in data['categories']

    def test_tv_videos_by_category(self, client, mock_db):
        """Test filtering videos by category."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchall.return_value = [
            (1, 'Gaming Video', 'gaming-video', 'gamer1', 200, 20, 10, 'gaming_thumb.jpg')
        ]

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/videos?category=Gaming')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'videos' in data
            mock_cursor.execute.assert_called()

    def test_tv_invalid_category(self, client, mock_db):
        """Test filtering with invalid category."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchall.return_value = []

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/videos?category=InvalidCategory')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data['videos']) == 0


class TestTVVideoDetails:
    """Test TV API video details endpoint."""

    def test_tv_video_details_success(self, client, mock_db):
        """Test getting video details for TV playback."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = (
            1, 'Video Title', 'video-slug', 'username', 'Video description',
            1000, 100, 50, '/path/to/video.mp4', 'thumb.jpg', 1609459200
        )

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/video/video-slug')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['title'] == 'Video Title'
            assert data['username'] == 'username'
            assert 'video_url' in data
            assert 'duration' in data

    def test_tv_video_details_not_found(self, client, mock_db):
        """Test getting details for non-existent video."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = None

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/video/nonexistent-slug')

            assert response.status_code == 404
            data = json.loads(response.data)
            assert 'error' in data

    def test_tv_video_playback_url(self, client, mock_db):
        """Test video playback URL for TV streaming."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = (
            1, 'Test Video', 'test-slug', 'user1', 'Description',
            1000, 100, 50, '/videos/test.mp4', 'thumb.jpg', 1609459200
        )

        with patch('bottube_server.get_db', return_value=mock_conn):
            response = client.get('/api/tv/video/test-slug/stream')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'stream_url' in data
            assert data['stream_url'].endswith('.mp4')


class TestTVAPIErrorHandling:
    """Test TV API error handling scenarios."""

    def test_tv_database_error(self, client):
        """Test handling database connection errors."""
        with patch('bottube_server.get_db', side_effect=Exception('Database error')):
            response = client.get('/api/tv/videos')

            assert response.status_code == 500
            data = json.loads(response.data)
            assert 'error' in data

    def test_tv_malformed_parameters(self, client):
        """Test handling malformed query parameters."""
        response = client.get('/api/tv/videos?page=invalid&limit=not_a_number')

        # Should default to reasonable values or return 400
        assert response.status_code in [200, 400]

    def test_tv_rate_limiting(self, client):
        """Test rate limiting for TV API endpoints."""
        # Simulate multiple rapid requests
        responses = []
        for _ in range(10):
            responses.append(client.get('/api/tv/videos'))

        # At least some should succeed
        success_count = sum(1 for r in responses if r.status_code == 200)
        assert success_count > 0


class TestTVAPIAuthentication:
    """Test TV API authentication and authorization."""

    def test_tv_public_endpoints(self, client):
        """Test that TV endpoints work without authentication."""
        endpoints = [
            '/api/tv/videos',
            '/api/tv/categories',
            '/api/tv/search?q=test'
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            # Should not require authentication
            assert response.status_code != 401

    def test_tv_analytics_tracking(self, client, mock_db):
        """Test that TV video views are properly tracked."""
        mock_conn, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = (
            1, 'Test Video', 'test-slug', 'user1', 'Description',
            1000, 100, 50, '/videos/test.mp4', 'thumb.jpg', 1609459200
        )

        with patch('bottube_server.get_db', return_value=mock_conn):
            # Simulate TV view tracking
            response = client.post('/api/tv/video/test-slug/view', json={
                'device_type': 'roku',
                'session_id': 'tv_session_123'
            })

            # Should track the view
            assert response.status_code in [200, 201]
