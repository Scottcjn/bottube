import sqlite3
import tempfile
import os
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask, g, session
import json
from datetime import datetime, timedelta

# Import the main application
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bottube_server import app, get_db

@pytest.fixture
def client():
    """Create test client with in-memory database"""
    db_fd, app.config['DATABASE'] = tempfile.mkstemp()
    app.config['TESTING'] = True

    with app.test_client() as client:
        with app.app_context():
            # Initialize test database
            conn = sqlite3.connect(app.config['DATABASE'])
            conn.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')

            conn.execute('''CREATE TABLE IF NOT EXISTS collaborations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                creator_id INTEGER NOT NULL,
                collaborator_id INTEGER,
                status TEXT DEFAULT 'pending',
                revenue_split REAL DEFAULT 50.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (creator_id) REFERENCES users (id),
                FOREIGN KEY (collaborator_id) REFERENCES users (id)
            )''')

            conn.execute('''CREATE TABLE IF NOT EXISTS collaboration_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collaboration_id INTEGER NOT NULL,
                invitee_email TEXT NOT NULL,
                invite_token TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (collaboration_id) REFERENCES collaborations (id)
            )''')

            conn.execute('''CREATE TABLE IF NOT EXISTS cross_promotions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collaboration_id INTEGER NOT NULL,
                promotion_type TEXT NOT NULL,
                content TEXT,
                scheduled_at TIMESTAMP,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (collaboration_id) REFERENCES collaborations (id)
            )''')

            # Insert test users
            conn.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                        ('creator1', 'creator1@test.com', 'hashed_password'))
            conn.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                        ('collaborator1', 'collab1@test.com', 'hashed_password'))
            conn.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                        ('testuser', 'test@example.com', 'hashed_password'))
            conn.commit()
            conn.close()

        yield client

    os.close(db_fd)
    os.unlink(app.config['DATABASE'])

def test_collaboration_creation(client):
    """Test creating a new collaboration project"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'creator1'

    response = client.post('/api/collaborations',
                          json={
                              'title': 'AI Tutorial Series',
                              'description': 'Educational content about AI tools',
                              'revenue_split': 60.0
                          })

    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['title'] == 'AI Tutorial Series'
    assert data['revenue_split'] == 60.0
    assert data['status'] == 'pending'
    assert data['creator_id'] == 1

def test_invitation_handling(client):
    """Test sending and accepting collaboration invitations"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'creator1'

    # Create collaboration first
    collab_response = client.post('/api/collaborations',
                                 json={'title': 'Test Collab', 'description': 'Test'})
    collab_data = json.loads(collab_response.data)
    collab_id = collab_data['id']

    # Send invitation
    invite_response = client.post(f'/api/collaborations/{collab_id}/invite',
                                 json={'email': 'collab1@test.com'})

    assert invite_response.status_code == 200
    invite_data = json.loads(invite_response.data)
    assert 'invite_token' in invite_data

    # Accept invitation (switch user context)
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['username'] = 'collaborator1'

    token = invite_data['invite_token']
    accept_response = client.post(f'/api/collaborations/accept/{token}')

    assert accept_response.status_code == 200
    accept_data = json.loads(accept_response.data)
    assert accept_data['status'] == 'active'

def test_revenue_sharing_calculations(client):
    """Test revenue split calculations and updates"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1

    # Create collaboration with custom revenue split
    response = client.post('/api/collaborations',
                          json={
                              'title': 'Revenue Test',
                              'description': 'Testing revenue splits',
                              'revenue_split': 70.0
                          })

    collab_data = json.loads(response.data)
    collab_id = collab_data['id']

    # Test revenue calculation endpoint
    calc_response = client.post(f'/api/collaborations/{collab_id}/calculate-revenue',
                               json={'total_revenue': 1000.00})

    assert calc_response.status_code == 200
    calc_data = json.loads(calc_response.data)
    assert calc_data['creator_share'] == 700.0  # 70% of 1000
    assert calc_data['collaborator_share'] == 300.0  # 30% of 1000

    # Test updating revenue split
    update_response = client.put(f'/api/collaborations/{collab_id}',
                                json={'revenue_split': 55.0})

    assert update_response.status_code == 200
    updated_data = json.loads(update_response.data)
    assert updated_data['revenue_split'] == 55.0

def test_project_status_updates(client):
    """Test collaboration status transitions"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1

    # Create collaboration
    response = client.post('/api/collaborations',
                          json={'title': 'Status Test', 'description': 'Testing status'})
    collab_data = json.loads(response.data)
    collab_id = collab_data['id']

    # Update status to in_progress
    status_response = client.put(f'/api/collaborations/{collab_id}/status',
                                json={'status': 'in_progress'})

    assert status_response.status_code == 200
    status_data = json.loads(status_response.data)
    assert status_data['status'] == 'in_progress'

    # Update to completed
    complete_response = client.put(f'/api/collaborations/{collab_id}/status',
                                  json={'status': 'completed'})

    assert complete_response.status_code == 200
    complete_data = json.loads(complete_response.data)
    assert complete_data['status'] == 'completed'

def test_cross_promotion_features(client):
    """Test cross-promotion content creation and scheduling"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1

    # Create collaboration
    collab_response = client.post('/api/collaborations',
                                 json={'title': 'Promo Test', 'description': 'Testing promotions'})
    collab_data = json.loads(collab_response.data)
    collab_id = collab_data['id']

    # Create cross-promotion
    future_date = (datetime.now() + timedelta(days=7)).isoformat()
    promo_response = client.post(f'/api/collaborations/{collab_id}/promotions',
                                json={
                                    'promotion_type': 'youtube_shoutout',
                                    'content': 'Check out this amazing collaboration!',
                                    'scheduled_at': future_date
                                })

    assert promo_response.status_code == 201
    promo_data = json.loads(promo_response.data)
    assert promo_data['promotion_type'] == 'youtube_shoutout'
    assert promo_data['status'] == 'draft'

    # Get promotions for collaboration
    list_response = client.get(f'/api/collaborations/{collab_id}/promotions')
    assert list_response.status_code == 200
    list_data = json.loads(list_response.data)
    assert len(list_data['promotions']) == 1

def test_error_handling(client):
    """Test error handling for various edge cases"""
    # Test unauthorized access
    response = client.post('/api/collaborations',
                          json={'title': 'Unauthorized Test'})
    assert response.status_code == 401

    with client.session_transaction() as sess:
        sess['user_id'] = 1

    # Test invalid collaboration ID
    response = client.get('/api/collaborations/999999')
    assert response.status_code == 404

    # Test invalid revenue split
    response = client.post('/api/collaborations',
                          json={
                              'title': 'Invalid Split',
                              'revenue_split': 150.0  # Invalid: > 100%
                          })
    assert response.status_code == 400

    # Test invalid status transition
    collab_response = client.post('/api/collaborations',
                                 json={'title': 'Status Error Test', 'description': 'Test'})
    collab_data = json.loads(collab_response.data)
    collab_id = collab_data['id']

    invalid_status_response = client.put(f'/api/collaborations/{collab_id}/status',
                                        json={'status': 'invalid_status'})
    assert invalid_status_response.status_code == 400

def test_database_operations(client):
    """Test database integrity and complex queries"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1

    # Create multiple collaborations
    for i in range(3):
        client.post('/api/collaborations',
                   json={'title': f'DB Test {i+1}', 'description': f'Testing DB ops {i+1}'})

    # Test listing user's collaborations
    list_response = client.get('/api/collaborations')
    assert list_response.status_code == 200
    list_data = json.loads(list_response.data)
    assert len(list_data['collaborations']) >= 3

    # Test filtering by status
    status_response = client.get('/api/collaborations?status=pending')
    assert status_response.status_code == 200
    status_data = json.loads(status_response.data)

    # All should be pending by default
    for collab in status_data['collaborations']:
        assert collab['status'] == 'pending'

    # Test database transaction rollback simulation
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        # Count collaborations before
        cursor.execute("SELECT COUNT(*) FROM collaborations WHERE creator_id = ?", (1,))
        count_before = cursor.fetchone()[0]

        # Verify count matches API response
        assert count_before >= 3
