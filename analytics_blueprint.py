# SPDX-License-Identifier: MIT
"""
BoTTube Creator Analytics Dashboard
Implements bounty #2157 / issue #423
Features: View trends, engagement metrics, top videos, audience breakdown, CSV export
"""

import sqlite3
import json
import csv
import io
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, render_template, jsonify, request, g, Response, session
from functools import wraps

analytics_bp = Blueprint('analytics', __name__, url_prefix='/analytics')


def get_db():
    """Get database connection from Flask app context or create new one."""
    if 'db' in g:
        return g.db
    # Fallback: create connection directly
    db = sqlite3.connect(str(Path(__file__).parent / "bottube.db"))
    db.row_factory = sqlite3.Row
    return db


def login_required(f):
    """Decorator to require login for analytics routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
        if not agent_id and 'agent_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function


@analytics_bp.route('/')
def analytics_dashboard():
    """Render the analytics dashboard page."""
    return render_template('analytics.html')


@analytics_bp.route('/api/views')
def api_views():
    """
    Get view count trends for a creator's videos.
    Query params:
    - period: '7d', '30d', '90d' (default: 30d)
    - video_id: specific video filter (optional)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    period = request.args.get('period', '30d')
    video_id = request.args.get('video_id')

    # Calculate date range
    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()

    # Get total views data
    if video_id:
        views_query = """
            SELECT DATE(timestamp, 'unixepoch') as date, COUNT(*) as views
            FROM video_views
            WHERE video_id = ? AND timestamp >= ?
            GROUP BY DATE(timestamp, 'unixepoch')
            ORDER BY date DESC
        """
        views_data = db.execute(views_query, (video_id, start_timestamp)).fetchall()
    else:
        views_query = """
            SELECT DATE(vv.timestamp, 'unixepoch') as date, COUNT(*) as views
            FROM video_views vv
            JOIN videos v ON vv.video_id = v.id
            WHERE v.uploader_id = ? AND vv.timestamp >= ?
            GROUP BY DATE(vv.timestamp, 'unixepoch')
            ORDER BY date DESC
        """
        views_data = db.execute(views_query, (agent_id, start_timestamp)).fetchall()

    return jsonify({
        "views": [{"date": row["date"], "count": row["views"]} for row in views_data]
    })


@analytics_bp.route('/api/engagement')
def api_engagement():
    """Get engagement metrics (likes, comments, shares) for creator's videos."""
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    period = request.args.get('period', '30d')
    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()

    # Get engagement data
    engagement_query = """
        SELECT
            DATE(l.created_at, 'unixepoch') as date,
            COUNT(CASE WHEN l.like_type = 'like' THEN 1 END) as likes,
            COUNT(CASE WHEN l.like_type = 'dislike' THEN 1 END) as dislikes
        FROM likes l
        JOIN videos v ON l.video_id = v.id
        WHERE v.uploader_id = ? AND l.created_at >= ?
        GROUP BY DATE(l.created_at, 'unixepoch')
        ORDER BY date DESC
    """

    engagement_data = db.execute(engagement_query, (agent_id, start_timestamp)).fetchall()

    return jsonify({
        "engagement": [{
            "date": row["date"],
            "likes": row["likes"],
            "dislikes": row["dislikes"]
        } for row in engagement_data]
    })


@analytics_bp.route('/api/top-videos')
def api_top_videos():
    """Get top performing videos for the creator."""
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    limit = request.args.get('limit', 10, type=int)

    db = get_db()

    top_videos_query = """
        SELECT
            v.id,
            v.title,
            v.views,
            COUNT(CASE WHEN l.like_type = 'like' THEN 1 END) as likes,
            COUNT(CASE WHEN l.like_type = 'dislike' THEN 1 END) as dislikes
        FROM videos v
        LEFT JOIN likes l ON v.id = l.video_id
        WHERE v.uploader_id = ?
        GROUP BY v.id, v.title, v.views
        ORDER BY v.views DESC
        LIMIT ?
    """

    top_videos = db.execute(top_videos_query, (agent_id, limit)).fetchall()

    return jsonify({
        "videos": [{
            "id": row["id"],
            "title": row["title"],
            "views": row["views"],
            "likes": row["likes"],
            "dislikes": row["dislikes"]
        } for row in top_videos]
    })


@analytics_bp.route('/api/export')
def api_export():
    """Export analytics data as CSV."""
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    export_type = request.args.get('type', 'views')
    period = request.args.get('period', '30d')

    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()

    output = io.StringIO()
    writer = csv.writer(output)

    if export_type == 'views':
        writer.writerow(['Date', 'Views'])
        views_query = """
            SELECT DATE(vv.timestamp, 'unixepoch') as date, COUNT(*) as views
            FROM video_views vv
            JOIN videos v ON vv.video_id = v.id
            WHERE v.uploader_id = ? AND vv.timestamp >= ?
            GROUP BY DATE(vv.timestamp, 'unixepoch')
            ORDER BY date DESC
        """
        data = db.execute(views_query, (agent_id, start_timestamp)).fetchall()
        for row in data:
            writer.writerow([row['date'], row['views']])

    elif export_type == 'engagement':
        writer.writerow(['Date', 'Likes', 'Dislikes'])
        engagement_query = """
            SELECT
                DATE(l.created_at, 'unixepoch') as date,
                COUNT(CASE WHEN l.like_type = 'like' THEN 1 END) as likes,
                COUNT(CASE WHEN l.like_type = 'dislike' THEN 1 END) as dislikes
            FROM likes l
            JOIN videos v ON l.video_id = v.id
            WHERE v.uploader_id = ? AND l.created_at >= ?
            GROUP BY DATE(l.created_at, 'unixepoch')
            ORDER BY date DESC
        """
        data = db.execute(engagement_query, (agent_id, start_timestamp)).fetchall()
        for row in data:
            writer.writerow([row['date'], row['likes'], row['dislikes']])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment;filename=analytics_{export_type}_{period}.csv"}
    )
