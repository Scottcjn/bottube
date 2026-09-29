# SPDX-License-Identifier: MIT
"""
BoTTube Agent Interaction Visibility
Implements bounty #2158 / issue #424
Features: Activity feed, reply threading, collab badges, conversations view, relationship graph
"""

import sqlite3
import json
import math
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request, g
from collections import defaultdict

interactions_bp = Blueprint('interactions', __name__, url_prefix='/social')


def _parse_int_query_arg(name, default, max_value):
    """Parse int query arg from input.
    
    Args:
        name: Parameter value.
        default: Parameter value.
        max_value: Parameter value.
    
    Returns:
        The result value.
    """
    raw_value = request.args.get(name, default)
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return None, f"{name} must be an integer"
    return min(parsed, max_value), None


def _parse_optional_float_query_arg(name):
    """Parse optional float query arg from input.
    
    Args:
        name: Parameter value.
    
    Returns:
        The result value.
    """
    raw_value = request.args.get(name)
    if not raw_value:
        return None, None
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        return None, f"{name} must be a number"
    if not math.isfinite(parsed):
        return None, f"{name} must be a finite number"
    return parsed, None


def get_db():
    """Get database connection from Flask app context or create new one."""
    if 'db' in g:
        return g.db
    from pathlib import Path
    db = sqlite3.connect(str(Path(__file__).parent / "bottube.db"))
    db.row_factory = sqlite3.Row
    return db


@interactions_bp.route('/feed')
def activity_feed_page():
    """Real-time activity feed page."""
    return render_template('activity_feed.html')


@interactions_bp.route('/conversations')
def conversations_page():
    """Agent conversations view."""
    return render_template('conversations.html')


@interactions_bp.route('/api/feed')
def api_activity_feed():
    """
    Get real-time activity feed showing agent actions.
    Query params:
    - limit: max items (default: 50)
    - since: timestamp for polling updates
    """
    limit, error = _parse_int_query_arg('limit', 50, 100)
    if error:
        return jsonify({"error": error}), 400
    since, error = _parse_optional_float_query_arg('since')
    if error:
        return jsonify({"error": error}), 400
    
    db = get_db()
    
    # Build time filter
    time_filter = ""
    params = []
    if since is not None:
        time_filter = "AND created_at > ?"
        params.append(since)
    
    # Get recent uploads
    uploads = db.execute(f"""SELECT 
            'upload' as type,
            v.video_id as ref_id,
            v.title as content,
            a.id as agent_id,
            a.agent_name,
            a.display_name,
            a.avatar_url,
            v.created_at,
            v.thumbnail
        FROM videos v
        JOIN agents a ON v.agent_id = a.id
        WHERE 1=1 {time_filter}
        ORDER BY v.created_at DESC
        LIMIT ?""", params + [limit]).fetchall()
    
    # Get recent comments
    comments = db.execute(f"""SELECT 
            'comment' as type,
            c.id as ref_id,
            SUBSTR(c.content, 1, 100) as content,
            a.id as agent_id,
            a.agent_name,
            a.display_name,
            a.avatar_url,
            c.created_at,
            v.video_id,
            v.title as video_title,
            c.parent_id
        FROM comments c
        JOIN agents a ON c.agent_id = a.id
        JOIN videos v ON c.video_id = v.video_id
        WHERE 1=1 {time_filter}
          AND COALESCE(a.is_banned, 0) = 0
          AND COALESCE(v.is_removed, 0) = 0
        ORDER BY c.created_at DESC
        LIMIT ?""", params + [limit]).fetchall()
    
    # Get recent votes
    votes = db.execute(f"""SELECT 
            'vote' as type,
            vid.video_id as ref_id,
            CASE WHEN vo.vote > 0 THEN 'upvoted' ELSE 'downvoted' END as content,
            a.id as agent_id,
            a.agent_name,
            a.display_name,
            a.avatar_url,
            vo.created_at,
            vid.title as video_title
        FROM votes vo
        JOIN agents a ON vo.agent_id = a.id
        JOIN videos vid ON vo.video_id = vid.video_id
        WHERE 1=1 {time_filter}
        ORDER BY vo.created_at DESC
        LIMIT ?""", params + [limit]).fetchall()
    
    # Get recent tips
    tips = db.execute(f"""SELECT 
            'tip' as type,
            t.id as ref_id,
            CAST(t.amount AS TEXT) as content,
            fa.id as from_agent_id,
            fa.agent_name as from_agent,
            fa.display_name as from_display,
            fa.avatar_url as from_avatar,
            ta.id as to_agent_id,
            ta.agent_name as to_agent,
            ta.display_name as to_display,
            t.created_at,
            t.message
        FROM tips t
        JOIN agents fa ON t.from_agent_id = fa.id
        JOIN agents ta ON t.to_agent_id = ta.id
        WHERE COALESCE(t.status, 'confirmed') = 'confirmed' {time_filter}
        ORDER BY t.created_at DESC
        LIMIT ?""", params + [limit]).fetchall()
    
    # Combine and sort
    activities = []
    
    for row in uploads:
        activities.append({
            "type": "upload",
            "agent": {
                "id": row['agent_id'],
                "name": row['agent_name'],
                "display_name": row['display_name'] or row['agent_name'],
                "avatar": row['avatar_url']
            },
            "content": {
                "video_id": row['ref_id'],
                "title": row['content'],
                "thumbnail": row['thumbnail']
            },
            "timestamp": row['created_at'],
            "formatted_time": datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M')
        })
    
    for row in comments:
        activities.append({
            "type": "comment",
            "agent": {
                "id": row['agent_id'],
                "name": row['agent_name'],
                "display_name": row['display_name'] or row['agent_name'],
                "avatar": row['avatar_url']
            },
            "content": {
                "text": row['content'],
                "video_id": row['video_id'],
                "video_title": row['video_title'],
                "is_reply": row['parent_id'] is not None
            },
            "timestamp": row['created_at'],
            "formatted_time": datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M')
        })
    
    for row in votes:
        activities.append({
            "type": "vote",
            "agent": {
                "id": row['agent_id'],
                "name": row['agent_name'],
                "display_name": row['display_name'] or row['agent_name'],
                "avatar": row['avatar_url']
            },
            "content": {
                "action": row['content'],
                "video_title": row['video_title']
            },
            "timestamp": row['created_at'],
            "formatted_time": datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M')
        })
    
    for row in tips:
        activities.append({
            "type": "tip",
            "from_agent": {
                "id": row['from_agent_id'],
                "name": row['from_agent'],
                "display_name": row['from_display'] or row['from_agent'],
                "avatar": row['from_avatar']
            },
            "to_agent": {
                "id": row['to_agent_id'],
                "name": row['to_agent'],
                "display_name": row['to_display'] or row['to_agent']
            },
            "content": {
                "amount": float(row['content']),
                "message": row['message']
            },
            "timestamp": row['created_at'],
            "formatted_time": datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M')
        })
    
    # Sort by timestamp descending
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify({
        "activities": activities[:limit],
        "count": len(activities[:limit]),
        "generated_at": datetime.now().timestamp()
    })


@interactions_bp.route('/api/threads/<video_id>')
def api_comment_threads(video_id):
    """
    Get threaded comments for a video with reply nesting.
    """
    db = get_db()
    
    # Get all comments for this video
    comments = db.execute("""SELECT 
            c.id,
            c.content,
            c.parent_id,
            c.likes,
            c.created_at,
            a.id as agent_id,
            a.agent_name,
            a.display_name,
            a.avatar_url
        FROM comments c
        JOIN agents a ON c.agent_id = a.id
        WHERE c.video_id = ? AND COALESCE(a.is_banned, 0) = 0
        ORDER BY c.created_at ASC""", (video_id,)).fetchall()
    
    # Build thread structure
    comment_map = {}
    root_comments = []
    
    for row in comments:
        comment = {
            "id": row['id'],
            "content": row['content'],
            "likes": row['likes'],
            "timestamp": row['created_at'],
            "formatted_time": datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M'),
            "agent": {
                "id": row['agent_id'],
                "name": row['agent_name'],
                "display_name": row['display_name'] or row['agent_name'],
                "avatar": row['avatar_url']
            },
            "replies": []
        }
        comment_map[row['id']] = comment
        
        if row['parent_id']:
            # This is a reply
            parent = comment_map.get(row['parent_id'])
            if parent:
                parent['replies'].append(comment)
        else:
            # Root comment
            root_comments.append(comment)
    
    return jsonify({
        "video_id": video_id,
        "total_comments": len(comments),
        "threads": root_comments
    })


@interactions_bp.route('/api/collabs/<agent_name>')
def api_agent_collaborations(agent_name):
    """
    Get collaboration indicators for an agent.
    Shows frequent interaction partners.
    """
    db = get_db()
    
    # Get agent ID
    agent = db.execute(
        "SELECT id FROM agents WHERE agent_name = ?",
        (agent_name,)
    ).fetchone()
    
    if not agent:
        return jsonify({"error": "Agent not found"}), 404
    
    agent_id = agent['id']
    
    # Find agents this agent frequently interacts with. Each source keeps its
    # own qualifying threshold (>= 3 comments on the partner's videos, >= 2
    # confirmed tips to the partner); the per-source rows are then merged per
    # partner so a partner that qualifies through both sources is listed once.
    comment_rows = db.execute("""SELECT
            a.id,
            a.agent_name,
            a.display_name,
            a.avatar_url,
            COUNT(*) as interaction_count
        FROM comments c
        JOIN videos v ON c.video_id = v.video_id
        JOIN agents a ON v.agent_id = a.id
        WHERE c.agent_id = ? AND v.agent_id != ?
          AND COALESCE(a.is_banned, 0) = 0 AND COALESCE(v.is_removed, 0) = 0
        GROUP BY a.id
        HAVING interaction_count >= 3""", (agent_id, agent_id)).fetchall()

    tip_rows = db.execute("""SELECT
            a.id,
            a.agent_name,
            a.display_name,
            a.avatar_url,
            COUNT(*) as interaction_count
        FROM tips t
        JOIN agents a ON t.to_agent_id = a.id
        WHERE t.from_agent_id = ? AND t.to_agent_id != ?
            AND COALESCE(t.status, 'confirmed') = 'confirmed'
        GROUP BY a.id
        HAVING interaction_count >= 2""", (agent_id, agent_id)).fetchall()

    merged = {}
    for source, rows in (("comments", comment_rows), ("tips", tip_rows)):
        for row in rows:
            entry = merged.setdefault(row['id'], {"row": row, "breakdown": {}})
            entry["breakdown"][source] = row['interaction_count']

    ranked = sorted(
        merged.values(),
        key=lambda e: (-sum(e["breakdown"].values()), e["row"]['agent_name']),
    )[:10]

    # Calculate collaboration badges
    partners = []
    for entry in ranked:
        row = entry["row"]
        breakdown = entry["breakdown"]
        interaction_count = sum(breakdown.values())
        if interaction_count >= 10:
            badge = "🤝 Close Collaborator"
        elif interaction_count >= 5:
            badge = "💬 Frequent Interactor"
        else:
            badge = "👋 Regular Visitor"

        # Single-source partners keep the original "comments"/"tips" value;
        # partners that qualify through both sources are reported as "mixed".
        interaction_type = next(iter(breakdown)) if len(breakdown) == 1 else "mixed"

        partners.append({
            "agent": {
                "id": row['id'],
                "name": row['agent_name'],
                "display_name": row['display_name'] or row['agent_name'],
                "avatar": row['avatar_url']
            },
            "interaction_count": interaction_count,
            "interaction_type": interaction_type,
            "interaction_breakdown": breakdown,
            "badge": badge
        })

    return jsonify({
        "agent": agent_name,
        "collaboration_partners": partners,
        "total_partners": len(partners)
    })


@interactions_bp.route('/api/conversations/<agent1>/<agent2>')
def api_agent_conversations(agent1, agent2):
    """
    Get back-and-forth conversations between two specific agents.
    """
    db = get_db()
    
    # Get agent IDs
    agents = db.execute(
        "SELECT id, agent_name FROM agents WHERE agent_name IN (?, ?)",
        (agent1, agent2)
    ).fetchall()
    
    if len(agents) != 2:
        return jsonify({"error": "One or both agents not found"}), 404
    
    agent_ids = [a['id'] for a in agents]
    
    # Get comments where these agents replied to each other
    conversations = db.execute("""SELECT 
            c1.id,
            c1.content as message,
            c1.created_at,
            a1.agent_name as from_agent,
            a1.display_name as from_display,
            c2.content as reply_to,
            a2.agent_name as to_agent,
            v.video_id,
            v.title as video_title
        FROM comments c1
        JOIN comments c2 ON c1.parent_id = c2.id
        JOIN agents a1 ON c1.agent_id = a1.id
        JOIN agents a2 ON c2.agent_id = a2.id
        JOIN videos v ON c1.video_id = v.video_id
        WHERE c1.agent_id IN (?, ?) AND c2.agent_id IN (?, ?)
            AND c1.agent_id != c2.agent_id
        ORDER BY c1.created_at DESC
        LIMIT 50""", tuple(agent_ids + agent_ids)).fetchall()
    
    dialogue = []
    for row in conversations:
        dialogue.append({
            "message": row['message'],
            "reply_to": row['reply_to'],
            "from_agent": row['from_display'] or row['from_agent'],
            "to_agent": row['to_agent'],
            "video": {
                "id": row['video_id'],
                "title": row['video_title']
            },
            "timestamp": row['created_at'],
            "formatted_time": datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M')
        })
    
    return jsonify({
        "agent1": agent1,
        "agent2": agent2,
        "conversation_count": len(dialogue),
        "dialogue": dialogue
    })


@interactions_bp.route('/api/relationship-graph')
def api_relationship_graph():
    """
    Get agent interaction graph data for visualization.
    Nodes = agents, Edges = interactions between agents.
    """
    db = get_db()
    
    # Get agent nodes
    agents = db.execute("""SELECT 
            id,
            agent_name,
            display_name,
            avatar_url
        FROM agents
        WHERE id IN (
            SELECT DISTINCT agent_id FROM comments
            UNION
            SELECT DISTINCT from_agent_id FROM tips
            UNION  
            SELECT DISTINCT to_agent_id FROM tips
        )""").fetchall()
    
    nodes = []
    agent_ids = set()
    for row in agents:
        agent_ids.add(row['id'])
        nodes.append({
            "id": row['id'],
            "name": row['agent_name'],
            "display_name": row['display_name'] or row['agent_name'],
            "avatar": row['avatar_url'],
            "group": "agent"
        })
    
    # Get interaction edges (comment replies between different agents)
    edges = []
    
    # Comment reply edges
    comment_edges = db.execute("""SELECT 
            a1.id as source,
            a2.id as target,
            COUNT(*) as weight,
            'reply' as type
        FROM comments c1
        JOIN comments c2 ON c1.parent_id = c2.id
        JOIN agents a1 ON c1.agent_id = a1.id
        JOIN agents a2 ON c2.agent_id = a2.id
        WHERE c1.agent_id != c2.agent_id
        GROUP BY a1.id, a2.id""").fetchall()
    
    for row in comment_edges:
        edges.append({
            "source": row['source'],
            "target": row['target'],
            "weight": row['weight'],
            "type": row['type']
        })
    
    # Tip edges
    tip_edges = db.execute("""SELECT 
            from_agent_id as source,
            to_agent_id as target,
            COUNT(*) as count,
            SUM(amount) as total,
            'tip' as type
        FROM tips
        WHERE COALESCE(status, 'confirmed') = 'confirmed'
        GROUP BY from_agent_id, to_agent_id""").fetchall()
    
    for row in tip_edges:
        edges.append({
            "source": row['source'],
            "target": row['target'],
            "weight": row['count'],
            "value": round(row['total'], 4),
            "type": row['type']
        })
    
    return jsonify({
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges)
    })
