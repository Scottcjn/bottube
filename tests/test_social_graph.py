tests/test_social_graph.py
```python
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Sample data representing interactions in the mock DB
# Requirements: At least 3 agents interacting
MOCK_INTERACTIONS_DATA = [
    {"sender": "AgentA", "receiver": "AgentB", "timestamp": "2023-10-01T10:00:00"},
    {"sender": "AgentA", "receiver": "AgentC", "timestamp": "2023-10-01T10:05:00"},
    {"sender": "AgentB", "receiver": "AgentC", "timestamp": "2023-10-01T10:10:00"},
    {"sender": "AgentC", "receiver": "AgentA", "timestamp": "2023-10-01T10:15:00"},
    {"sender": "AgentB", "receiver": "AgentA", "timestamp": "2023-10-01T10:20:00"},
    {"sender": "AgentA", "receiver": "AgentB", "timestamp": "2023-10-01T10:25:00"},
]

# Paths to patch. 
# NOTE: These paths assume a standard structure 'app.api.social'. 
# Adjust 'app.api.social.get_interactions' and 'app.api.social.check_agent_exists' 
# to match the actual module paths in the application.
PATCH_GET_INTERACTIONS = 'app.api.social.get_interactions'
PATCH_CHECK_AGENT = 'app.api.social.check_agent_exists'

@pytest.fixture
def mock_data():
    return MOCK_INTERACTIONS_DATA

def test_social_graph_structure(client, mock_data):
    """
    Test /api/social/graph returns network, top_pairs, most_connected.
    """
    with patch(PATCH_GET_INTERACTIONS, return_value=mock_data):
        response = client.get("/api/social/graph")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify required keys
        assert "network" in data
        assert "top_pairs" in data
        assert "most_connected" in data
        
        # Verify network structure
        assert "nodes" in data["network"]
        assert "links" in data["network"]
        
        # Verify we have the expected agents
        node_ids = [node["id"] for node in data["network"]["nodes"]]
        assert "AgentA" in node_ids
        assert "AgentB" in node_ids
        assert "AgentC" in node_ids
        
        # Verify most_connected has entries
        assert len(data["most_connected"]) > 0

def test_agent_interactions_structure(client, mock_data):
    """
    Test /api/agents/<name>/interactions returns incoming and outgoing.
    """
    agent_name = "AgentA"
    
    with patch(PATCH_GET_INTERACTIONS, return_value=mock_data):
        with patch(PATCH_CHECK_AGENT, return_value=True):
            response = client.get(f"/api/agents/{agent_name}/interactions")
            assert response.status_code == 200
            
            data = response.json()
            
            assert "incoming" in data
            assert "outgoing" in data
            
            # AgentA sends 3 times (to B twice, to C once)
            assert len(data["outgoing"]) == 3
            # AgentA receives 2 times (from C, from B)
            assert len(data["incoming"]) == 2

def test_agent_interactions_limit(client, mock_data):
    """
    Test limit parameter works for interactions endpoint.
    """
    agent_name = "AgentA"
    limit = 1
    
    with patch(PATCH_GET_INTERACTIONS, return_value=mock_data):
        with patch(PATCH_CHECK_AGENT, return_value=True):
            response = client.get(f"/api/agents/{agent_name}/interactions?limit={limit}")
            assert response.status_code == 200
            
            data = response.json()
            
            # Verify the limit is respected
            assert len(data["outgoing"]) <= limit
            assert len(data["incoming"]) <= limit

def test_agent_not_found(client):
    """
    Test 404 for nonexistent agent.
    """
    agent_name = "NonExistentAgent"
    
    with patch(PATCH_CHECK_AGENT, return_value=False):
        response = client.get(f"/api/agents/{agent_name}/interactions")
        assert response.status_code == 404
```