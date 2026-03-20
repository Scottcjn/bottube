import os
import tempfile
import sqlite3
import json
import pytest
from bottube_server import app


class TestSocialGraph:
    @pytest.fixture
    def client(self):
        db_fd, app.config['DATABASE'] = tempfile.mkstemp()
        app.config['TESTING'] = True
        client = app.test_client()

        with app.app_context():
            self._init_db()
            self._seed_test_data()

        yield client

        os.close(db_fd)
        os.unlink(app.config['DATABASE'])

    def _init_db(self):
        with sqlite3.connect(app.config['DATABASE']) as db:
            db.execute('''
                CREATE TABLE IF NOT EXISTS agents (
                    name TEXT PRIMARY KEY,
                    type TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            db.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subscriber TEXT NOT NULL,
                    target TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (subscriber) REFERENCES agents (name),
                    FOREIGN KEY (target) REFERENCES agents (name)
                )
            ''')
            db.commit()

    def _seed_test_data(self):
        with sqlite3.connect(app.config['DATABASE']) as db:
            # Create test agents
            agents = [
                ('alice_bot', 'content'),
                ('bob_trader', 'trading'),
                ('charlie_news', 'news'),
                ('diana_crypto', 'analysis'),
                ('eve_social', 'social')
            ]
            db.executemany('INSERT INTO agents (name, type) VALUES (?, ?)', agents)

            # Create subscription network
            subscriptions = [
                ('alice_bot', 'bob_trader'),
                ('alice_bot', 'charlie_news'),
                ('bob_trader', 'alice_bot'),
                ('bob_trader', 'diana_crypto'),
                ('charlie_news', 'alice_bot'),
                ('charlie_news', 'diana_crypto'),
                ('charlie_news', 'eve_social'),
                ('diana_crypto', 'bob_trader'),
                ('diana_crypto', 'eve_social'),
                ('eve_social', 'alice_bot'),
                ('eve_social', 'charlie_news')
            ]
            db.executemany('INSERT INTO subscriptions (subscriber, target) VALUES (?, ?)', subscriptions)
            db.commit()

    def test_social_graph_basic(self, client):
        response = client.get('/api/social/graph')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'nodes' in data
        assert 'edges' in data
        assert 'stats' in data

        # Verify nodes structure
        assert len(data['nodes']) == 5
        for node in data['nodes']:
            assert 'id' in node
            assert 'type' in node
            assert 'followers' in node
            assert 'following' in node

        # Verify edges structure
        assert len(data['edges']) == 11
        for edge in data['edges']:
            assert 'source' in edge
            assert 'target' in edge

    def test_social_graph_with_limit(self, client):
        response = client.get('/api/social/graph?limit=3')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert len(data['nodes']) <= 3

    def test_social_graph_limit_bounds(self, client):
        # Test minimum bound
        response = client.get('/api/social/graph?limit=0')
        assert response.status_code == 400

        # Test maximum bound
        response = client.get('/api/social/graph?limit=101')
        assert response.status_code == 400

        # Test invalid format
        response = client.get('/api/social/graph?limit=invalid')
        assert response.status_code == 400

    def test_agent_interactions_basic(self, client):
        response = client.get('/api/agents/alice_bot/interactions')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'agent' in data
        assert 'incoming' in data
        assert 'outgoing' in data
        assert 'stats' in data

        assert data['agent'] == 'alice_bot'
        assert len(data['incoming']) >= 0
        assert len(data['outgoing']) >= 0

    def test_agent_interactions_with_limit(self, client):
        response = client.get('/api/agents/charlie_news/interactions?limit=2')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert len(data['incoming']) <= 2
        assert len(data['outgoing']) <= 2

    def test_agent_interactions_nonexistent(self, client):
        response = client.get('/api/agents/nonexistent_bot/interactions')
        assert response.status_code == 404

    def test_agent_interactions_limit_validation(self, client):
        response = client.get('/api/agents/alice_bot/interactions?limit=-1')
        assert response.status_code == 400

        response = client.get('/api/agents/alice_bot/interactions?limit=51')
        assert response.status_code == 400

    def test_social_graph_network_structure(self, client):
        response = client.get('/api/social/graph')
        data = json.loads(response.data)

        # Verify alice_bot has correct connections
        alice_node = next(n for n in data['nodes'] if n['id'] == 'alice_bot')
        assert alice_node['followers'] == 3  # bob, charlie, eve
        assert alice_node['following'] == 2  # bob, charlie

        # Verify stats calculations
        stats = data['stats']
        assert 'total_agents' in stats
        assert 'total_connections' in stats
        assert 'avg_connections' in stats
        assert stats['total_agents'] == 5
        assert stats['total_connections'] == 11

    def test_interaction_data_structure(self, client):
        response = client.get('/api/agents/diana_crypto/interactions')
        data = json.loads(response.data)

        # Verify incoming/outgoing structure
        for interaction in data['incoming'] + data['outgoing']:
            assert 'agent' in interaction
            assert 'created_at' in interaction

        # Verify stats
        stats = data['stats']
        assert 'incoming_count' in stats
        assert 'outgoing_count' in stats
        assert 'total_interactions' in stats
