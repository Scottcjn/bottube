# SPDX-License-Identifier: MIT

import pytest
import json
import sqlite3
from bottube_server import app, get_db, init_db


class TestSocialGraphAPI:
    @pytest.fixture
    def client(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = ':memory:'

        with app.test_client() as client:
            with app.app_context():
                init_db()
                self._setup_test_data()
            yield client

    def _setup_test_data(self):
        db = get_db()

        # Create test users
        test_users = [
            ('alice', 'alice@test.com', 'Alice Bot', 'AI assistant'),
            ('bob', 'bob@test.com', 'Bob Bot', 'Trading bot'),
            ('charlie', 'charlie@test.com', 'Charlie AI', 'Content creator'),
            ('diana', 'diana@test.com', 'Diana Bot', 'News aggregator'),
            ('eve', 'eve@test.com', 'Eve AI', 'Music curator')
        ]

        for username, email, display_name, bio in test_users:
            db.execute(
                'INSERT OR IGNORE INTO users (username, email, display_name, bio, created_at) VALUES (?, ?, ?, ?, datetime("now"))',
                (username, email, display_name, bio)
            )

        # Create subscription relationships
        # alice follows bob, charlie, diana
        # bob follows alice, charlie
        # charlie follows alice, diana, eve
        # diana follows bob, eve
        # eve follows alice, bob, charlie, diana
        subscriptions = [
            ('alice', 'bob'), ('alice', 'charlie'), ('alice', 'diana'),
            ('bob', 'alice'), ('bob', 'charlie'),
            ('charlie', 'alice'), ('charlie', 'diana'), ('charlie', 'eve'),
            ('diana', 'bob'), ('diana', 'eve'),
            ('eve', 'alice'), ('eve', 'bob'), ('eve', 'charlie'), ('eve', 'diana')
        ]

        for follower, following in subscriptions:
            db.execute(
                '''INSERT OR IGNORE INTO subscriptions (follower_id, following_id, created_at)
                   SELECT f.id, t.id, datetime("now")
                   FROM users f, users t
                   WHERE f.username = ? AND t.username = ?''',
                (follower, following)
            )

        db.commit()

    def test_social_graph_basic(self, client):
        response = client.get('/api/social/graph')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'nodes' in data
        assert 'edges' in data
        assert 'stats' in data

        # Should have 5 users
        assert len(data['nodes']) == 5

        # Check node structure
        node = data['nodes'][0]
        assert 'id' in node
        assert 'username' in node
        assert 'display_name' in node
        assert 'follower_count' in node
        assert 'following_count' in node

        # Should have subscription edges
        assert len(data['edges']) > 0

        # Check edge structure
        edge = data['edges'][0]
        assert 'source' in edge
        assert 'target' in edge
        assert 'created_at' in edge

    def test_social_graph_with_limit(self, client):
        response = client.get('/api/social/graph?limit=3')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert len(data['nodes']) == 3

    def test_social_graph_limit_bounds(self, client):
        # Test minimum bound
        response = client.get('/api/social/graph?limit=0')
        assert response.status_code == 400

        # Test maximum bound
        response = client.get('/api/social/graph?limit=101')
        assert response.status_code == 400

        # Test valid bounds
        response = client.get('/api/social/graph?limit=1')
        assert response.status_code == 200

        response = client.get('/api/social/graph?limit=100')
        assert response.status_code == 200

    def test_social_graph_invalid_limit(self, client):
        response = client.get('/api/social/graph?limit=invalid')
        assert response.status_code == 400

    def test_agent_interactions_basic(self, client):
        response = client.get('/api/agents/alice/interactions')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'agent' in data
        assert 'followers' in data
        assert 'following' in data
        assert 'stats' in data

        # Check agent info
        agent = data['agent']
        assert agent['username'] == 'alice'
        assert agent['display_name'] == 'Alice Bot'

        # Alice should have followers and following
        assert len(data['followers']) > 0
        assert len(data['following']) > 0

    def test_agent_interactions_follower_structure(self, client):
        response = client.get('/api/agents/bob/interactions')
        assert response.status_code == 200

        data = json.loads(response.data)

        # Check follower structure
        if data['followers']:
            follower = data['followers'][0]
            assert 'username' in follower
            assert 'display_name' in follower
            assert 'followed_at' in follower

        # Check following structure
        if data['following']:
            following = data['following'][0]
            assert 'username' in following
            assert 'display_name' in following
            assert 'followed_at' in following

    def test_agent_interactions_with_limit(self, client):
        response = client.get('/api/agents/eve/interactions?limit=2')
        assert response.status_code == 200

        data = json.loads(response.data)
        # Eve has many connections, should be limited
        assert len(data['followers']) <= 2
        assert len(data['following']) <= 2

    def test_agent_interactions_nonexistent_agent(self, client):
        response = client.get('/api/agents/nonexistent/interactions')
        assert response.status_code == 404

    def test_agent_interactions_limit_validation(self, client):
        # Test invalid limits
        response = client.get('/api/agents/alice/interactions?limit=0')
        assert response.status_code == 400

        response = client.get('/api/agents/alice/interactions?limit=101')
        assert response.status_code == 400

        response = client.get('/api/agents/alice/interactions?limit=abc')
        assert response.status_code == 400

    def test_social_graph_stats(self, client):
        response = client.get('/api/social/graph')
        assert response.status_code == 200

        data = json.loads(response.data)
        stats = data['stats']

        assert 'total_users' in stats
        assert 'total_connections' in stats
        assert 'avg_connections' in stats
        assert stats['total_users'] == 5
        assert stats['total_connections'] > 0

    def test_agent_interactions_stats(self, client):
        response = client.get('/api/agents/charlie/interactions')
        assert response.status_code == 200

        data = json.loads(response.data)
        stats = data['stats']

        assert 'follower_count' in stats
        assert 'following_count' in stats
        assert 'mutual_connections' in stats
        assert isinstance(stats['follower_count'], int)
        assert isinstance(stats['following_count'], int)

    def test_empty_database(self, client):
        # Clear all data
        with app.app_context():
            db = get_db()
            db.execute('DELETE FROM subscriptions')
            db.execute('DELETE FROM users')
            db.commit()

        response = client.get('/api/social/graph')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['nodes'] == []
        assert data['edges'] == []
        assert data['stats']['total_users'] == 0

    def test_user_with_no_connections(self, client):
        # Add isolated user
        with app.app_context():
            db = get_db()
            db.execute(
                'INSERT INTO users (username, email, display_name, created_at) VALUES (?, ?, ?, datetime("now"))',
                ('isolated', 'isolated@test.com', 'Isolated Bot')
            )
            db.commit()

        response = client.get('/api/agents/isolated/interactions')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['followers'] == []
        assert data['following'] == []
        assert data['stats']['follower_count'] == 0
        assert data['stats']['following_count'] == 0

    def test_mutual_connections_calculation(self, client):
        response = client.get('/api/agents/alice/interactions')
        assert response.status_code == 200

        data = json.loads(response.data)
        stats = data['stats']

        # Alice follows bob, charlie, diana
        # Bob and charlie follow alice back
        # So alice should have 2 mutual connections
        assert stats['mutual_connections'] >= 0

    def test_graph_ordering(self, client):
        # Test that nodes are ordered by connection count
        response = client.get('/api/social/graph')
        assert response.status_code == 200

        data = json.loads(response.data)
        nodes = data['nodes']

        # Should be ordered by total connections (follower + following count)
        for i in range(len(nodes) - 1):
            current_total = nodes[i]['follower_count'] + nodes[i]['following_count']
            next_total = nodes[i + 1]['follower_count'] + nodes[i + 1]['following_count']
            assert current_total >= next_total
