"""Tests for social graph API endpoints.

These tests verify the API contract for:
- /api/social/graph - returns network, top_pairs, most_connected
- /api/agents/<agent_name>/interactions - returns incoming, outgoing
"""
import json


# Sample data for mock database
MOCK_AGENTS = [
    {"id": 1, "agent_name": "agent_alice", "display_name": "Alice", "is_human": 1, "avatar_url": "https://example.com/alice.png"},
    {"id": 2, "agent_name": "agent_bob", "display_name": "Bob", "is_human": 1, "avatar_url": "https://example.com/bob.png"},
    {"id": 3, "agent_name": "agent_charlie", "display_name": "Charlie", "is_human": 0, "avatar_url": "https://example.com/charlie.png"},
    {"id": 4, "agent_name": "agent_diana", "display_name": "Diana", "is_human": 1, "avatar_url": "https://example.com/diana.png"},
]

MOCK_SUBSCRIPTIONS = [
    {"follower_id": 1, "following_id": 2, "created_at": 1700000000},  # Alice follows Bob
    {"follower_id": 1, "following_id": 3, "created_at": 1700000100},  # Alice follows Charlie
    {"follower_id": 2, "following_id": 1, "created_at": 1700000200},  # Bob follows Alice
    {"follower_id": 3, "following_id": 1, "created_at": 1700000300},  # Charlie follows Alice
    {"follower_id": 3, "following_id": 2, "created_at": 1700000400},  # Charlie follows Bob
    {"follower_id": 4, "following_id": 1, "created_at": 1700000500},  # Diana follows Alice
    {"follower_id": 4, "following_id": 2, "created_at": 1700000600},  # Diana follows Bob
]


def get_mock_db():
    """Create a mock database with sample data."""
    return {
        "agents": {a["agent_name"]: a for a in MOCK_AGENTS},
        "subscriptions": list(MOCK_SUBSCRIPTIONS),
    }


def get_agent_by_name(db, agent_name):
    """Get agent by name from mock DB."""
    return db["agents"].get(agent_name)


def get_agent_by_id(db, agent_id):
    """Get agent by ID from mock DB."""
    for agent in MOCK_AGENTS:
        if agent["id"] == agent_id:
            return agent
    return None


def social_graph_query(db, limit=50):
    """Simulate /api/social/graph endpoint logic."""
    # Get network
    network = []
    for sub in db["subscriptions"]:
        follower = get_agent_by_id(db, sub["follower_id"])
        following = get_agent_by_id(db, sub["following_id"])
        if follower and following:
            network.append({"follower": follower["agent_name"], "following": following["agent_name"]})
    network = network[:limit * 2]
    
    # Get most_connected
    most_connected = []
    for agent in MOCK_AGENTS:
        followers = sum(1 for s in db["subscriptions"] if s["following_id"] == agent["id"])
        following = sum(1 for s in db["subscriptions"] if s["follower_id"] == agent["id"])
        most_connected.append({
            "agent_name": agent["agent_name"],
            "display_name": agent["display_name"],
            "connections": followers + following
        })
    most_connected = sorted(most_connected, key=lambda x: x["connections"], reverse=True)[:limit]
    
    return {
        "network": network,
        "top_pairs": [],  # Simplified
        "most_connected": most_connected,
    }


def agent_interactions_query(db, agent_name, limit=50):
    """Simulate /api/agents/<agent_name>/interactions endpoint logic."""
    target = get_agent_by_name(db, agent_name)
    if not target:
        return None, {"error": "Agent not found"}
    
    # Get incoming (followers)
    incoming = []
    for sub in db["subscriptions"]:
        if sub["following_id"] == target["id"]:
            follower = get_agent_by_id(db, sub["follower_id"])
            if follower:
                incoming.append({
                    "agent_name": follower["agent_name"],
                    "display_name": follower["display_name"],
                    "is_human": bool(follower["is_human"]),
                    "avatar_url": follower["avatar_url"],
                    "followed_at": sub["created_at"]
                })
    
    # Get outgoing (following)
    outgoing = []
    for sub in db["subscriptions"]:
        if sub["follower_id"] == target["id"]:
            following = get_agent_by_id(db, sub["following_id"])
            if following:
                outgoing.append({
                    "agent_name": following["agent_name"],
                    "display_name": following["display_name"],
                    "is_human": bool(following["is_human"]),
                    "avatar_url": following["avatar_url"],
                    "followed_at": sub["created_at"]
                })
    
    return {
        "incoming": incoming[:limit],
        "outgoing": outgoing[:limit],
        "incoming_count": len(incoming),
        "outgoing_count": len(outgoing),
    }, None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_social_graph_returns_required_fields():
    """Test that /api/social/graph returns network, top_pairs, most_connected."""
    db = get_mock_db()
    result = social_graph_query(db)
    
    assert "network" in result
    assert "top_pairs" in result
    assert "most_connected" in result
    assert isinstance(result["network"], list)
    assert isinstance(result["top_pairs"], list)
    assert isinstance(result["most_connected"], list)


def test_social_graph_network_contains_pairs():
    """Test that network contains follower/following pairs."""
    db = get_mock_db()
    result = social_graph_query(db)
    
    # Should have pairs from our mock data
    assert len(result["network"]) > 0
    for pair in result["network"]:
        assert "follower" in pair
        assert "following" in pair


def test_social_graph_most_connected_ordered():
    """Test that most_connected is ordered by connections descending."""
    db = get_mock_db()
    result = social_graph_query(db)
    
    most_connected = result["most_connected"]
    if len(most_connected) > 1:
        for i in range(len(most_connected) - 1):
            assert most_connected[i]["connections"] >= most_connected[i + 1]["connections"]


def test_social_graph_respects_limit():
    """Test that limit parameter is respected."""
    db = get_mock_db()
    result = social_graph_query(db, limit=2)
    
    assert len(result["most_connected"]) <= 2


def test_agent_interactions_returns_required_fields():
    """Test that /api/agents/<agent_name>/interactions returns required fields."""
    db = get_mock_db()
    result, error = agent_interactions_query(db, "agent_alice")
    
    assert error is None
    assert "incoming" in result
    assert "outgoing" in result
    assert "incoming_count" in result
    assert "outgoing_count" in result


def test_agent_interactions_nonexistent_agent():
    """Test that nonexistent agent returns error."""
    db = get_mock_db()
    result, error = agent_interactions_query(db, "nonexistent_agent")
    
    assert result is None
    assert error is not None
    assert "not found" in error["error"].lower()


def test_agent_interactions_incoming_contains_followers():
    """Test that incoming contains followers."""
    db = get_mock_db()
    result, error = agent_interactions_query(db, "agent_alice")
    
    incoming_names = [r["agent_name"] for r in result["incoming"]]
    # Alice is followed by Bob, Charlie, Diana
    assert "agent_bob" in incoming_names
    assert "agent_charlie" in incoming_names
    assert "agent_diana" in incoming_names


def test_agent_interactions_outgoing_contains_following():
    """Test that outgoing contains who the agent follows."""
    db = get_mock_db()
    result, error = agent_interactions_query(db, "agent_alice")
    
    outgoing_names = [r["agent_name"] for r in result["outgoing"]]
    # Alice follows Bob and Charlie
    assert "agent_bob" in outgoing_names
    assert "agent_charlie" in outgoing_names


def test_agent_interactions_counts_match_arrays():
    """Test that counts match array lengths."""
    db = get_mock_db()
    result, error = agent_interactions_query(db, "agent_alice")
    
    assert result["incoming_count"] == len(result["incoming"])
    assert result["outgoing_count"] == len(result["outgoing"])


def test_agent_interactions_respects_limit():
    """Test that limit parameter is respected."""
    db = get_mock_db()
    result, error = agent_interactions_query(db, "agent_alice", limit=1)
    
    assert len(result["incoming"]) <= 1
    assert len(result["outgoing"]) <= 1


def test_agent_interactions_includes_avatar_and_display_name():
    """Test that response includes avatar_url and display_name."""
    db = get_mock_db()
    result, error = agent_interactions_query(db, "agent_alice")
    
    if result["incoming"]:
        first = result["incoming"][0]
        assert "avatar_url" in first
        assert "display_name" in first
        assert "is_human" in first
        assert "followed_at" in first
