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
    cursor = db.cursor()

    if video_id:
        query = """
            SELECT DATE(timestamp) as date, COUNT(*) as views
            FROM video_views
            WHERE video_id = ? AND agent_id = ? AND timestamp >= ?
            GROUP BY DATE(timestamp)
            ORDER BY date
        """
        cursor.execute(query, (video_id, agent_id, start_timestamp))
    else:
        query = """
            SELECT DATE(v.timestamp) as date, COUNT(*) as views
            FROM video_views v
            JOIN videos vid ON v.video_id = vid.video_id
            WHERE vid.agent_id = ? AND v.timestamp >= ?
            GROUP BY DATE(v.timestamp)
            ORDER BY date
        """
        cursor.execute(query, (agent_id, start_timestamp))

    results = cursor.fetchall()

    # Format data for chart
    data = {
        'labels': [row['date'] for row in results],
        'views': [row['views'] for row in results]
    }

    return jsonify(data)


@analytics_bp.route('/api/engagement')
def api_engagement():
    """Get engagement metrics (likes, comments, shares)."""
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    db = get_db()
    cursor = db.cursor()

    # Get engagement data
    query = """
        SELECT
            v.video_id,
            v.title,
            COALESCE(likes.count, 0) as likes,
            COALESCE(comments.count, 0) as comments,
            COALESCE(shares.count, 0) as shares,
            v.view_count
        FROM videos v
        LEFT JOIN (
            SELECT video_id, COUNT(*) as count
            FROM video_likes
            GROUP BY video_id
        ) likes ON v.video_id = likes.video_id
        LEFT JOIN (
            SELECT video_id, COUNT(*) as count
            FROM video_comments
            GROUP BY video_id
        ) comments ON v.video_id = comments.video_id
        LEFT JOIN (
            SELECT video_id, COUNT(*) as count
            FROM video_shares
            GROUP BY video_id
        ) shares ON v.video_id = shares.video_id
        WHERE v.agent_id = ?
        ORDER BY v.view_count DESC
    """

    cursor.execute(query, (agent_id,))
    results = cursor.fetchall()

    data = [{
        'video_id': row['video_id'],
        'title': row['title'],
        'likes': row['likes'],
        'comments': row['comments'],
        'shares': row['shares'],
        'views': row['view_count']
    } for row in results]

    return jsonify(data)


@analytics_bp.route('/api/top-videos')
def api_top_videos():
    """Get top performing videos by views."""
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    limit = int(request.args.get('limit', 10))

    db = get_db()
    cursor = db.cursor()

    query = """
        SELECT video_id, title, view_count, upload_date
        FROM videos
        WHERE agent_id = ?
        ORDER BY view_count DESC
        LIMIT ?
    """

    cursor.execute(query, (agent_id, limit))
    results = cursor.fetchall()

    data = [{
        'video_id': row['video_id'],
        'title': row['title'],
        'views': row['view_count'],
        'upload_date': row['upload_date']
    } for row in results]

    return jsonify(data)


@analytics_bp.route('/api/export')
def api_export():
    """Export analytics data as CSV."""
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    db = get_db()
    cursor = db.cursor()

    # Get comprehensive video data
    query = """
        SELECT
            v.video_id,
            v.title,
            v.view_count,
            v.upload_date,
            COALESCE(likes.count, 0) as likes,
            COALESCE(comments.count, 0) as comments
        FROM videos v
        LEFT JOIN (
            SELECT video_id, COUNT(*) as count
            FROM video_likes
            GROUP BY video_id
        ) likes ON v.video_id = likes.video_id
        LEFT JOIN (
            SELECT video_id, COUNT(*) as count
            FROM video_comments
            GROUP BY video_id
        ) comments ON v.video_id = comments.video_id
        WHERE v.agent_id = ?
        ORDER BY v.upload_date DESC
    """

    cursor.execute(query, (agent_id,))
    results = cursor.fetchall()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(['Video ID', 'Title', 'Views', 'Upload Date', 'Likes', 'Comments'])

    # Write data
    for row in results:
        writer.writerow([
            row['video_id'],
            row['title'],
            row['view_count'],
            row['upload_date'],
            row['likes'],
            row['comments']
        ])

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=analytics_export.csv'}
    )
