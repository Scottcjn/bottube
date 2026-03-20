# SPDX-License-Identifier: MIT

import pytest
import json
from unittest.mock import patch, MagicMock
from bottube_server import app, get_db


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['DATABASE'] = ':memory:'
    with app.test_client() as client:
        with app.app_context():
            db = get_db()
            # Create basic schema for testing
            db.execute('''CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                filename TEXT NOT NULL,
                upload_date TEXT NOT NULL,
                votes_up INTEGER DEFAULT 0,
                votes_down INTEGER DEFAULT 0,
                category TEXT DEFAULT 'general'
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER,
                ip_address TEXT,
                vote_type TEXT,
                created_at TEXT,
                FOREIGN KEY (video_id) REFERENCES videos (id)
            )''')
            db.commit()
        yield client


def test_extension_manifest_serving(client):
    """Test that extension manifest.json is served correctly"""
    response = client.get('/extension/manifest.json')
    assert response.status_code == 200
    assert response.content_type == 'application/json'

    # Verify CORS headers
    assert 'Access-Control-Allow-Origin' in response.headers
    assert 'Access-Control-Allow-Methods' in response.headers


def test_extension_static_files(client):
    """Test serving of extension static files"""
    # Test CSS file serving
    response = client.get('/extension/popup.css')
    if response.status_code == 200:
        assert 'text/css' in response.content_type
        assert 'Access-Control-Allow-Origin' in response.headers

    # Test JavaScript file serving
    response = client.get('/extension/popup.js')
    if response.status_code == 200:
        assert 'application/javascript' in response.content_type
        assert 'Access-Control-Allow-Origin' in response.headers


def test_api_trending_videos(client):
    """Test API endpoint for trending videos"""
    # Insert test data
    db = get_db()
    db.execute('''INSERT INTO videos (title, description, filename, upload_date, votes_up, votes_down)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               ('Trending Video 1', 'Test description', 'test1.mp4', '2024-01-15', 25, 3))
    db.execute('''INSERT INTO videos (title, description, filename, upload_date, votes_up, votes_down)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               ('Trending Video 2', 'Another test', 'test2.mp4', '2024-01-16', 15, 1))
    db.commit()

    response = client.get('/api/videos/trending')
    assert response.status_code == 200
    assert response.content_type == 'application/json'

    data = json.loads(response.data)
    assert 'videos' in data
    assert len(data['videos']) <= 10  # Should limit results


def test_api_recent_videos(client):
    """Test API endpoint for recent videos"""
    # Insert test data with different dates
    db = get_db()
    db.execute('''INSERT INTO videos (title, description, filename, upload_date, votes_up)
                  VALUES (?, ?, ?, ?, ?)''',
               ('Recent Video', 'Latest upload', 'recent.mp4', '2024-01-20', 5))
    db.commit()

    response = client.get('/api/videos/recent')
    assert response.status_code == 200
    assert response.content_type == 'application/json'

    data = json.loads(response.data)
    assert 'videos' in data
    assert isinstance(data['videos'], list)


def test_api_search_videos(client):
    """Test video search API endpoint"""
    # Insert searchable test data
    db = get_db()
    db.execute('''INSERT INTO videos (title, description, filename, upload_date)
                  VALUES (?, ?, ?, ?)''',
               ('Python Tutorial', 'Learn Python basics', 'python.mp4', '2024-01-10'))
    db.execute('''INSERT INTO videos (title, description, filename, upload_date)
                  VALUES (?, ?, ?, ?)''',
               ('JavaScript Guide', 'Frontend development', 'js.mp4', '2024-01-11'))
    db.commit()

    response = client.get('/api/videos/search?q=python')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'videos' in data
    assert len(data['videos']) >= 1

    # Test empty search
    response = client.get('/api/videos/search?q=')
    assert response.status_code == 400


def test_api_vote_endpoint(client):
    """Test video voting API"""
    # Insert test video
    db = get_db()
    cursor = db.execute('''INSERT INTO videos (title, filename, upload_date)
                          VALUES (?, ?, ?)''',
                        ('Test Video', 'test.mp4', '2024-01-15'))
    video_id = cursor.lastrowid
    db.commit()

    # Test upvote
    response = client.post(f'/api/videos/{video_id}/vote',
                          json={'vote_type': 'up'})
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'success' in data
    assert data['success'] is True

    # Verify vote was recorded
    cursor = db.execute('SELECT votes_up FROM videos WHERE id = ?', (video_id,))
    result = cursor.fetchone()
    assert result[0] == 1


def test_api_vote_invalid_video(client):
    """Test voting on non-existent video"""
    response = client.post('/api/videos/999/vote',
                          json={'vote_type': 'up'})
    assert response.status_code == 404


def test_api_vote_invalid_type(client):
    """Test invalid vote type"""
    db = get_db()
    cursor = db.execute('''INSERT INTO videos (title, filename, upload_date)
                          VALUES (?, ?, ?)''',
                        ('Test Video', 'test.mp4', '2024-01-15'))
    video_id = cursor.lastrowid
    db.commit()

    response = client.post(f'/api/videos/{video_id}/vote',
                          json={'vote_type': 'invalid'})
    assert response.status_code == 400


def test_cors_headers_on_api_endpoints(client):
    """Test that all API endpoints include proper CORS headers"""
    endpoints = [
        '/api/videos/trending',
        '/api/videos/recent',
        '/api/videos/search?q=test'
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert 'Access-Control-Allow-Origin' in response.headers
        assert 'Access-Control-Allow-Methods' in response.headers
        assert 'Access-Control-Allow-Headers' in response.headers


def test_options_preflight_requests(client):
    """Test CORS preflight OPTIONS requests"""
    response = client.options('/api/videos/trending')
    assert response.status_code == 200
    assert 'Access-Control-Allow-Origin' in response.headers
    assert 'Access-Control-Allow-Methods' in response.headers


def test_api_stats_endpoint(client):
    """Test API endpoint for extension stats"""
    # Insert test data
    db = get_db()
    db.execute('''INSERT INTO videos (title, filename, upload_date)
                  VALUES (?, ?, ?)''',
               ('Video 1', 'v1.mp4', '2024-01-15'))
    db.execute('''INSERT INTO videos (title, filename, upload_date)
                  VALUES (?, ?, ?)''',
               ('Video 2', 'v2.mp4', '2024-01-16'))
    db.commit()

    response = client.get('/api/stats')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'total_videos' in data
    assert data['total_videos'] >= 2


def test_api_categories_endpoint(client):
    """Test API endpoint for video categories"""
    # Insert videos with different categories
    db = get_db()
    db.execute('''INSERT INTO videos (title, filename, upload_date, category)
                  VALUES (?, ?, ?, ?)''',
               ('Tech Video', 'tech.mp4', '2024-01-15', 'technology'))
    db.execute('''INSERT INTO videos (title, filename, upload_date, category)
                  VALUES (?, ?, ?, ?)''',
               ('Music Video', 'music.mp4', '2024-01-15', 'music'))
    db.commit()

    response = client.get('/api/categories')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'categories' in data
    assert isinstance(data['categories'], list)


def test_error_handling_invalid_json(client):
    """Test error handling for invalid JSON in POST requests"""
    response = client.post('/api/videos/1/vote',
                          data='invalid json',
                          content_type='application/json')
    assert response.status_code == 400


@patch('bottube_server.get_db')
def test_database_error_handling(mock_get_db, client):
    """Test graceful handling of database errors"""
    mock_db = MagicMock()
    mock_db.execute.side_effect = Exception("Database error")
    mock_get_db.return_value = mock_db

    response = client.get('/api/videos/trending')
    assert response.status_code == 500


def test_rate_limiting_considerations(client):
    """Test that endpoints can handle multiple rapid requests"""
    # Make several rapid requests to test stability
    for _ in range(5):
        response = client.get('/api/videos/trending')
        assert response.status_code in [200, 429]  # 429 if rate limited


def test_extension_notification_count(client):
    """Test API for extension notification badge count"""
    # Insert recent videos
    db = get_db()
    db.execute('''INSERT INTO videos (title, filename, upload_date)
                  VALUES (?, ?, ?)''',
               ('New Video', 'new.mp4', '2024-01-20'))
    db.commit()

    response = client.get('/api/notifications/count')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'count' in data
    assert isinstance(data['count'], int)
