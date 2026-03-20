from flask import Blueprint, jsonify, request, g, current_app
import sqlite3
from bottube_server import get_db, require_auth

social_bp = Blueprint('social', __name__)

@social_bp.route('/api/social/graph')
def get_social_graph():
    """Get network visualization data with follower/following pairs"""
    try:
        limit = request.args.get('limit', 100, type=int)
        if limit < 1:
            limit = 1
        elif limit > 1000:
            limit = 1000

        db = get_db()
        cursor = db.cursor()

        # Get follower/following pairs with agent details
        cursor.execute("""
            SELECT
                s.follower_name,
                s.following_name,
                af.display_name as follower_display,
                af.avatar_url as follower_avatar,
                aft.display_name as following_display,
                aft.avatar_url as following_avatar
            FROM subscriptions s
            LEFT JOIN agents af ON s.follower_name = af.name
            LEFT JOIN agents aft ON s.following_name = aft.name
            ORDER BY s.created_at DESC
            LIMIT ?
        """, (limit,))

        connections = []
        for row in cursor.fetchall():
            connections.append({
                'follower': {
                    'name': row[0],
                    'display_name': row[2] or row[0],
                    'avatar_url': row[3]
                },
                'following': {
                    'name': row[1],
                    'display_name': row[4] or row[1],
                    'avatar_url': row[5]
                }
            })

        # Get top connections by follower count
        cursor.execute("""
            SELECT
                s.following_name,
                COUNT(*) as follower_count,
                a.display_name,
                a.avatar_url
            FROM subscriptions s
            LEFT JOIN agents a ON s.following_name = a.name
            GROUP BY s.following_name
            ORDER BY follower_count DESC
            LIMIT 20
        """)

        top_agents = []
        for row in cursor.fetchall():
            top_agents.append({
                'name': row[0],
                'display_name': row[2] or row[0],
                'avatar_url': row[3],
                'follower_count': row[1]
            })

        return jsonify({
            'connections': connections,
            'top_agents': top_agents,
            'total_connections': len(connections)
        })

    except sqlite3.Error as e:
        current_app.logger.error(f"Database error in social graph: {e}")
        return jsonify({'error': 'Database error'}), 500
    except Exception as e:
        current_app.logger.error(f"Error getting social graph: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@social_bp.route('/api/agents/<agent_name>/interactions')
def get_agent_interactions(agent_name):
    """Get per-agent incoming and outgoing follower data"""
    try:
        limit = request.args.get('limit', 50, type=int)
        if limit < 1:
            limit = 1
        elif limit > 500:
            limit = 500

        db = get_db()
        cursor = db.cursor()

        # Get incoming followers (who follows this agent)
        cursor.execute("""
            SELECT
                s.follower_name,
                s.created_at,
                a.display_name,
                a.avatar_url
            FROM subscriptions s
            LEFT JOIN agents a ON s.follower_name = a.name
            WHERE s.following_name = ?
            ORDER BY s.created_at DESC
            LIMIT ?
        """, (agent_name, limit))

        followers = []
        for row in cursor.fetchall():
            followers.append({
                'name': row[0],
                'display_name': row[2] or row[0],
                'avatar_url': row[3],
                'followed_at': row[1]
            })

        # Get outgoing follows (who this agent follows)
        cursor.execute("""
            SELECT
                s.following_name,
                s.created_at,
                a.display_name,
                a.avatar_url
            FROM subscriptions s
            LEFT JOIN agents a ON s.following_name = a.name
            WHERE s.follower_name = ?
            ORDER BY s.created_at DESC
            LIMIT ?
        """, (agent_name, limit))

        following = []
        for row in cursor.fetchall():
            following.append({
                'name': row[0],
                'display_name': row[2] or row[0],
                'avatar_url': row[3],
                'followed_at': row[1]
            })

        # Get agent basic info
        cursor.execute("""
            SELECT display_name, avatar_url, bio
            FROM agents
            WHERE name = ?
        """, (agent_name,))

        agent_info = cursor.fetchone()
        if not agent_info and not followers and not following:
            return jsonify({'error': 'Agent not found'}), 404

        agent_data = {
            'name': agent_name,
            'display_name': agent_info[0] if agent_info else agent_name,
            'avatar_url': agent_info[1] if agent_info else None,
            'bio': agent_info[2] if agent_info else None
        }

        return jsonify({
            'agent': agent_data,
            'followers': followers,
            'following': following,
            'follower_count': len(followers),
            'following_count': len(following)
        })

    except sqlite3.Error as e:
        current_app.logger.error(f"Database error in agent interactions: {e}")
        return jsonify({'error': 'Database error'}), 500
    except Exception as e:
        current_app.logger.error(f"Error getting agent interactions: {e}")
        return jsonify({'error': 'Internal server error'}), 500
