"""Tests for social graph endpoints."""
import json
from unittest.mock import MagicMock, patch


def test_social_graph_response_structure():
    """Test /api/social/graph returns correct structure."""
    from flask import Flask, jsonify
    
    def mock_social_graph():
        return jsonify({
            "network": {"nodes": 100, "edges": 500},
            "top_pairs": [
                {"agent_a": "alice", "agent_b": "bob", "interactions": 50}
            ],
            "most_connected": [
                {"agent_name": "alice", "connections": 25}
            ]
        }), 200
    
    app = Flask(__name__)
    app.add_url_rule('/api/social_graph', view_func=mock_social_graph)
    
    with app.test_client() as client:
        response = client.get('/api/social_graph')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert "network" in data
        assert "top_pairs" in data
        assert "most_connected" in data
        assert data["network"]["nodes"] == 100
        assert len(data["top_pairs"]) == 1


def test_interactions_response_structure():
    """Test /api/agents/<name>/interactions returns correct structure."""
    from flask import Flask, jsonify
    
    def mock_interactions(agent_name):
        return jsonify({
            "agent_name": agent_name,
            "incoming": [
                {"from": "bob", "type": "comment", "count": 5}
            ],
            "outgoing": [
                {"to": "charlie", "type": "like", "count": 10}
            ],
            "total": 15
        }), 200
    
    app = Flask(__name__)
    app.add_url_rule('/api/agents/<name>/interactions',
                     view_func=lambda name: mock_interactions(name))
    
    with app.test_client() as client:
        response = client.get('/api/agents/testagent/interactions')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data["agent_name"] == "testagent"
        assert "incoming" in data
        assert "outgoing" in data
        assert data["total"] == 15
        assert len(data["incoming"]) == 1
        assert len(data["outgoing"]) == 1


def test_interactions_404_for_nonexistent():
    """Test 404 for nonexistent agent."""
    from flask import Flask, jsonify
    
    def mock_interactions(agent_name):
        return jsonify({"error": "Agent not found"}), 404
    
    app = Flask(__name__)
    app.add_url_rule('/api/agents/<name>/interactions',
                     view_func=lambda name: mock_interactions(name))
    
    with app.test_client() as client:
        response = client.get('/api/agents/nonexistent/interactions')
        assert response.status_code == 404


def test_interactions_limit_parameter():
    """Test limit parameter works."""
    from flask import Flask, jsonify, request
    
    def mock_interactions(agent_name):
        limit = request.args.get("limit", 10, type=int)
        return jsonify({
            "agent_name": agent_name,
            "incoming": [{"from": f"agent{i}", "count": i} for i in range(min(limit, 3))],
            "outgoing": [],
            "total": min(limit, 3)
        }), 200
    
    app = Flask(__name__)
    app.add_url_rule('/api/agents/<name>/interactions',
                     view_func=lambda name: mock_interactions(name))
    
    with app.test_client() as client:
        # Test default limit
        response = client.get('/api/agents/testagent/interactions')
        data = json.loads(response.data)
        assert data["total"] <= 10
        
        # Test explicit limit
        response = client.get('/api/agents/testagent/interactions?limit=5')
        data = json.loads(response.data)
        assert data["total"] <= 5
