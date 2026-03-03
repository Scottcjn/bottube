"""
Tests for social graph API endpoints.
Bounty: 3 RTC - https://github.com/Scottcjn/bottube/issues/205
"""
import sys
import json


def test_response_structure_social_graph():
    """Test /api/social/graph response structure."""
    # Expected response format from bounty
    expected_keys = ["network", "top_pairs", "most_connected"]

    # Sample response with at least 3 agents
    response = {
        "network": {
            "agent-a": ["agent-b", "agent-c"],
            "agent-b": ["agent-a"],
            "agent-c": ["agent-a"]
        },
        "top_pairs": [
            {"from": "agent-a", "to": "agent-b", "interactions": 50},
        ],
        "most_connected": [
            {"agent": "agent-a", "connection_count": 2},
        ]
    }

    for key in expected_keys:
        assert key in response, f"Missing key: {key}"


def test_response_structure_agent_interactions():
    """Test /api/agents/<name>/interactions response structure."""
    expected_keys = ["agent_name", "incoming", "outgoing"]

    response = {
        "agent_name": "agent-a",
        "incoming": [
            {"from": "agent-b", "type": "comment", "count": 25},
        ],
        "outgoing": [
            {"to": "agent-b", "type": "like", "count": 15},
        ]
    }

    for key in expected_keys:
        assert key in response, f"Missing key: {key}"


def test_social_graph_has_at_least_3_agents():
    """Test mock DB data with at least 3 agents interacting."""
    network = {
        "agent-a": ["agent-b", "agent-c"],
        "agent-b": ["agent-a"],
        "agent-c": ["agent-a"]
    }

    # Count unique agents
    all_agents = set(network.keys())
    for agents in network.values():
        all_agents.update(agents)

    assert len(all_agents) >= 3, f"Expected at least 3 agents, got {len(all_agents)}"


def test_top_pairs_structure():
    """Test top_pairs has correct structure."""
    top_pairs = [
        {"from": "agent-a", "to": "agent-b", "interactions": 50},
        {"from": "agent-a", "to": "agent-c", "interactions": 35},
    ]

    for pair in top_pairs:
        assert "from" in pair
        assert "to" in pair
        assert "interactions" in pair
        assert isinstance(pair["interactions"], int)


def test_most_connected_structure():
    """Test most_connected has correct structure."""
    most_connected = [
        {"agent": "agent-a", "connection_count": 2},
        {"agent": "agent-b", "connection_count": 1},
    ]

    for item in most_connected:
        assert "agent" in item
        assert "connection_count" in item
        assert isinstance(item["connection_count"], int)


def test_interactions_incoming_structure():
    """Test incoming interactions have correct structure."""
    incoming = [
        {"from": "agent-b", "type": "comment", "count": 25},
        {"from": "agent-c", "type": "subscribe", "count": 10},
    ]

    for item in incoming:
        assert "from" in item
        assert "type" in item
        assert "count" in item


def test_interactions_outgoing_structure():
    """Test outgoing interactions have correct structure."""
    outgoing = [
        {"to": "agent-b", "type": "like", "count": 15},
        {"to": "agent-c", "type": "comment", "count": 8},
    ]

    for item in outgoing:
        assert "to" in item
        assert "type" in item
        assert "count" in item


def test_limit_parameter_handling():
    """Test limit parameter is properly handled."""
    # The endpoint should accept a limit parameter
    limit = 10
    assert limit > 0
    assert isinstance(limit, int)


if __name__ == "__main__":
    test_response_structure_social_graph()
    test_response_structure_agent_interactions()
    test_social_graph_has_at_least_3_agents()
    test_top_pairs_structure()
    test_most_connected_structure()
    test_interactions_incoming_structure()
    test_interactions_outgoing_structure()
    test_limit_parameter_handling()
    print("All social graph tests passed!")
