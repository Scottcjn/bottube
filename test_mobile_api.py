# SPDX-License-Identifier: MIT
import pytest
import json
import os
import tempfile
import sqlite3
import bcrypt
from unittest.mock import patch
from flask import Flask
from mobile_api import mobile_api
from mobile_integration import setup_mobile_integration


@pytest.fixture
def app():
    # Create test app
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'

    # Set up test database
    db_fd, app.config['DATABASE'] = tempfile.mkstemp()

    with app.app_context():
        init_test_db()

    # Set up mobile integration
    setup_mobile_integration(app)

    yield app

    os.close(db_fd)
    os.unlink(app.config['DATABASE'])


@pytest.fixture
def client(app):
    return app.test_client()


def init_test_db():
    """Initialize test database with required tables."""
    db = sqlite3.connect(tempfile.gettempdir() + '/test.db')
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            joined TEXT
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            creator TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            upload_date TEXT,
            thumbnail TEXT
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY,
            video_id INTEGER,
            user_id INTEGER,
            username TEXT,
            content TEXT,
            created_at TEXT
        )
    ''')

    # Add test data
    password_hash = bcrypt.hashpw('password123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.execute(
        'INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
        ('testuser', password_hash, 'test@example.com')
    )

    db.execute(
        'INSERT INTO videos (title, description, creator) VALUES (?, ?, ?)',
        ('Test Video', 'A test video', 'testuser')
    )

    db.commit()
    db.close()


class TestMobileAuth:
    @patch.dict(os.environ, {'JWT_SECRET': 'test-jwt-secret'})
    def test_login_success(self, client):
        response = client.post('/api/mobile/auth/login',
                             json={'username': 'testuser', 'password': 'password123'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'token' in data
        assert 'user' in data
        assert data['user']['username'] == 'testuser'

    def test_login_missing_jwt_secret(self, client):
        response = client.post('/api/mobile/auth/login',
                             json={'username': 'testuser', 'password': 'password123'})
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'Server configuration error' in data['error']

    def test_login_invalid_credentials(self, client):
        with patch.dict(os.environ, {'JWT_SECRET': 'test-jwt-secret'}):
            response = client.post('/api/mobile/auth/login',
                                 json={'username': 'testuser', 'password': 'wrongpassword'})
            assert response.status_code == 401
            data = json.loads(response.data)
            assert data['error'] == 'Invalid credentials'

    def test_login_missing_data(self, client):
        response = client.post('/api/mobile/auth/login', json={})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Username and password required' in data['error']

    def test_login_invalid_json(self, client):
        response = client.post('/api/mobile/auth/login', data='invalid json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['error'] == 'Invalid JSON'


class TestMobileRegister:
    @patch.dict(os.environ, {'JWT_SECRET': 'test-jwt-secret'})
    def test_register_success(self, client):
        response = client.post('/api/mobile/auth/register',
                             json={'username': 'newuser', 'password': 'newpassword123', 'email': 'new@example.com'})
        assert response.status_code == 201
        data = json.loads(response.data)
        assert 'token' in data
        assert data['user']['username'] == 'newuser'

    def test_register_weak_password(self, client):
        response = client.post('/api/mobile/auth/register',
                             json={'username': 'newuser', 'password': '123'})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Password must be at least 8 characters' in data['error']

    def test_register_existing_user(self, client):
        with patch.dict(os.environ, {'JWT_SECRET': 'test-jwt-secret'}):
            response = client.post('/api/mobile/auth/register',
                                 json={'username': 'testuser', 'password': 'password123'})
            assert response.status_code == 409
            data = json.loads(response.data)
            assert data['error'] == 'Username already exists'


class TestMobileVideos:
    def get_auth_token(self, client):
        with patch.dict(os.environ, {'JWT_SECRET': 'test-jwt-secret'}):
            response = client.post('/api/mobile/auth/login',
                                 json={'username': 'testuser', 'password': 'password123'})
            return json.loads(response.data)['token']

    def test_get_videos_success(self, client):
        token = self.get_auth_token(client)
        response = client.get('/api/mobile/videos',
                            headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'videos' in data
        assert isinstance(data['videos'], list)

    def test_get_videos_no_token(self, client):
        response = client.get('/api/mobile/videos')
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data['error'] == 'Token is missing'

    def test_get_videos_invalid_token(self, client):
        response = client.get('/api/mobile/videos',
                            headers={'Authorization': 'Bearer invalid-token'})
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data['error'] == 'Token is invalid'


class TestRateLimiting:
    def test_rate_limit_exceeded(self, client):
        # Mock rate limit store to simulate exceeded limit
        from api_middleware import rate_limit_store
        rate_limit_store.set('127.0.0.1', 100)

        response = client.get('/api/mobile/videos')
        assert response.status_code == 429

        # Clean up
        rate_limit_store.data.clear()
