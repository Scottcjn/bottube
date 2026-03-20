from flask import Blueprint, request, jsonify, g
from werkzeug.exceptions import BadRequest, NotFound
from database import get_db

social_graph_bp = Blueprint('social_graph', __name__)

@social_graph_bp.route('/api/social/graph')
def get_social_graph():
    """Get network visualization data with follower/following pairs"""
    limit = request.args.get('limit', 50, type=int)

    # Bounds checking for limit parameter
    if limit < 1:
        limit = 1
    elif limit > 500:
        limit = 500

    db = get_db()

    # Get follower/following pairs with agent names
    graph_query = '''
        SELECT
            s.subscriber_id,
            s.agent_id,
            sub_agent.name as subscriber_name,
            target_agent.name as agent_name
        FROM subscriptions s
        JOIN agents sub_agent ON s.subscriber_id = sub_agent.id
        JOIN agents target_agent ON s.agent_id = target_agent.id
        ORDER BY s.created_at DESC
        LIMIT ?
    '''

    connections = db.execute(graph_query, (limit,)).fetchall()

    # Get top connections by follower count
    top_agents_query = '''
        SELECT
            a.name,
            a.id,
            COUNT(s.subscriber_id) as follower_count
        FROM agents a
        LEFT JOIN subscriptions s ON a.id = s.agent_id
        GROUP BY a.id, a.name
        ORDER BY follower_count DESC
        LIMIT 20
    '''

    top_agents = db.execute(top_agents_query).fetchall()

    # Build response data
    edges = []
    nodes = set()

    for conn in connections:
        edges.append({
            'source': conn['subscriber_name'],
            'target': conn['agent_name'],
            'subscriber_id': conn['subscriber_id'],
            'agent_id': conn['agent_id']
        })
        nodes.add(conn['subscriber_name'])
        nodes.add(conn['agent_name'])

    response_data = {
        'edges': edges,
        'nodes': list(nodes),
        'top_connections': [
            {
                'name': agent['name'],
                'id': agent['id'],
                'followers': agent['follower_count']
            }
            for agent in top_agents
        ],
        'total_edges': len(edges),
        'limit_applied': limit
    }

    return jsonify(response_data)

@social_graph_bp.route('/api/agents/<agent_name>/interactions')
def get_agent_interactions(agent_name):
    """Get per-agent incoming/outgoing follower data"""
    limit = request.args.get('limit', 100, type=int)

    # Bounds checking
    if limit < 1:
        limit = 1
    elif limit > 1000:
        limit = 1000

    db = get_db()

    # Check if agent exists
    agent = db.execute(
        'SELECT id, name FROM agents WHERE name = ?',
        (agent_name,)
    ).fetchone()

    if not agent:
        raise NotFound(f"Agent '{agent_name}' not found")

    # Get incoming followers (who follows this agent)
    incoming_query = '''
        SELECT
            s.subscriber_id,
            s.created_at,
            a.name as follower_name
        FROM subscriptions s
        JOIN agents a ON s.subscriber_id = a.id
        WHERE s.agent_id = ?
        ORDER BY s.created_at DESC
        LIMIT ?
    '''

    incoming = db.execute(incoming_query, (agent['id'], limit)).fetchall()

    # Get outgoing follows (who this agent follows)
    outgoing_query = '''
        SELECT
            s.agent_id,
            s.created_at,
            a.name as following_name
        FROM subscriptions s
        JOIN agents a ON s.agent_id = a.id
        WHERE s.subscriber_id = ?
        ORDER BY s.created_at DESC
        LIMIT ?
    '''

    outgoing = db.execute(outgoing_query, (agent['id'], limit)).fetchall()

    # Get total counts
    follower_count = db.execute(
        'SELECT COUNT(*) as count FROM subscriptions WHERE agent_id = ?',
        (agent['id'],)
    ).fetchone()['count']

    following_count = db.execute(
        'SELECT COUNT(*) as count FROM subscriptions WHERE subscriber_id = ?',
        (agent['id'],)
    ).fetchone()['count']

    response_data = {
        'agent': {
            'id': agent['id'],
            'name': agent['name']
        },
        'followers': [
            {
                'id': row['subscriber_id'],
                'name': row['follower_name'],
                'followed_at': row['created_at']
            }
            for row in incoming
        ],
        'following': [
            {
                'id': row['agent_id'],
                'name': row['following_name'],
                'followed_at': row['created_at']
            }
            for row in outgoing
        ],
        'stats': {
            'total_followers': follower_count,
            'total_following': following_count,
            'followers_shown': len(incoming),
            'following_shown': len(outgoing)
        },
        'limit_applied': limit
    }

    return jsonify(response_data)
