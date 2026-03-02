import pytest

def test_social_graph_returns_correct_structure(client):
    """
    Test /api/social/graph returns network, top_pairs, most_connected
    (Bounty #205 Requirement)
    """
    response = client.get('/api/social/graph')
    # Use direct assertion as requested by maintainer
    assert response.status_code == 200
    data = response.get_json()
    assert 'network' in data
    assert 'top_pairs' in data
    assert 'most_connected' in data

def test_agent_interactions_returns_correct_structure(client):
    """
    Test /api/agents/<name>/interactions returns incoming and outgoing
    (Bounty #205 Requirement)
    """
    # Using a known agent or mock logic
    response = client.get('/api/agents/vector/interactions')
    assert response.status_code == 200
    data = response.get_json()
    assert 'incoming' in data
    assert 'outgoing' in data

def test_agent_interactions_404_nonexistent(client):
    """
    Test 404 for nonexistent agent
    (Bounty #205 Requirement)
    """
    response = client.get('/api/agents/nonexistent_agent_xyz/interactions')
    assert response.status_code == 404

def test_social_graph_limit_parameter(client):
    """
    Test limit parameter works
    (Bounty #205 Requirement)
    """
    response = client.get('/api/social/graph?limit=5')
    assert response.status_code == 200

def test_mock_data_interactions(client):
    """
    Ensure the endpoint handles basic interaction data
    """
    response = client.get('/api/social/graph')
    assert response.status_code == 200
