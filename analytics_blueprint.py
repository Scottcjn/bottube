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

    # Get total views
    try:
        cursor = db.cursor()
        if video_id:
            cursor.execute("""
                SELECT COUNT(*) as view_count, DATE(created_at) as date
                FROM video_views
                WHERE video_id = ? AND created_at >= ?
                GROUP BY DATE(created_at)
                ORDER BY date
            """, (video_id, start_timestamp))
        else:
            cursor.execute("""
                SELECT COUNT(*) as view_count, DATE(vv.created_at) as date
                FROM video_views vv
                JOIN videos v ON vv.video_id = v.id
                WHERE v.user_id = ? AND vv.created_at >= ?
                GROUP BY DATE(vv.created_at)
                ORDER BY date
            """, (agent_id, start_timestamp))

        results = cursor.fetchall()
        return jsonify({
            "success": True,
            "data": [dict(row) for row in results],
            "period": period
        })
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/engagement')
def api_engagement():
    """
    Get engagement metrics (likes, comments, shares) for a creator's videos.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    period = request.args.get('period', '30d')
    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()

    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT v.id, v.title, v.view_count,
                   COUNT(DISTINCT l.id) as like_count,
                   COUNT(DISTINCT c.id) as comment_count
            FROM videos v
            LEFT JOIN likes l ON v.id = l.video_id AND l.created_at >= ?
            LEFT JOIN comments c ON v.id = c.video_id AND c.created_at >= ?
            WHERE v.user_id = ?
            GROUP BY v.id, v.title, v.view_count
            ORDER BY v.view_count DESC
            LIMIT 10
        """, (start_timestamp, start_timestamp, agent_id))

        results = cursor.fetchall()
        return jsonify({
            "success": True,
            "data": [dict(row) for row in results],
            "period": period
        })
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/top-videos')
def api_top_videos():
    """
    Get top performing videos for a creator.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    limit = request.args.get('limit', 10, type=int)

    db = get_db()

    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT v.id, v.title, v.description, v.view_count, v.created_at,
                   COUNT(DISTINCT l.id) as like_count,
                   COUNT(DISTINCT c.id) as comment_count
            FROM videos v
            LEFT JOIN likes l ON v.id = l.video_id
            LEFT JOIN comments c ON v.id = c.video_id
            WHERE v.user_id = ?
            GROUP BY v.id, v.title, v.description, v.view_count, v.created_at
            ORDER BY v.view_count DESC
            LIMIT ?
        """, (agent_id, limit))

        results = cursor.fetchall()
        return jsonify({
            "success": True,
            "data": [dict(row) for row in results]
        })
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/audience')
def api_audience():
    """
    Get audience demographics and viewing patterns.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    db = get_db()

    try:
        cursor = db.cursor()
        # Get viewing patterns by hour
        cursor.execute("""
            SELECT strftime('%H', vv.created_at) as hour,
                   COUNT(*) as view_count
            FROM video_views vv
            JOIN videos v ON vv.video_id = v.id
            WHERE v.user_id = ?
            GROUP BY hour
            ORDER BY hour
        """, (agent_id,))

        hourly_views = cursor.fetchall()

        # Get top viewers
        cursor.execute("""
            SELECT u.username, COUNT(*) as view_count
            FROM video_views vv
            JOIN videos v ON vv.video_id = v.id
            JOIN users u ON vv.user_id = u.id
            WHERE v.user_id = ?
            GROUP BY u.id, u.username
            ORDER BY view_count DESC
            LIMIT 10
        """, (agent_id,))

        top_viewers = cursor.fetchall()

        return jsonify({
            "success": True,
            "hourly_views": [dict(row) for row in hourly_views],
            "top_viewers": [dict(row) for row in top_viewers]
        })
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/export')
def api_export():
    """
    Export analytics data as CSV.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    export_type = request.args.get('type', 'videos')

    db = get_db()

    try:
        cursor = db.cursor()

        if export_type == 'videos':
            cursor.execute("""
                SELECT v.id, v.title, v.description, v.view_count, v.created_at,
                       COUNT(DISTINCT l.id) as like_count,
                       COUNT(DISTINCT c.id) as comment_count
                FROM videos v
                LEFT JOIN likes l ON v.id = l.video_id
                LEFT JOIN comments c ON v.id = c.video_id
                WHERE v.user_id = ?
                GROUP BY v.id, v.title, v.description, v.view_count, v.created_at
                ORDER BY v.view_count DESC
            """, (agent_id,))
        elif export_type == 'views':
            cursor.execute("""
                SELECT vv.created_at, v.title, u.username as viewer
                FROM video_views vv
                JOIN videos v ON vv.video_id = v.id
                LEFT JOIN users u ON vv.user_id = u.id
                WHERE v.user_id = ?
                ORDER BY vv.created_at DESC
            """, (agent_id,))
        else:
            return jsonify({"error": "Invalid export type"}), 400

        results = cursor.fetchall()

        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        if results:
            writer.writerow(results[0].keys())

            # Write data
            for row in results:
                writer.writerow(row)

        # Create response
        response_data = output.getvalue()
        output.close()

        return Response(
            response_data,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=analytics_{export_type}_{datetime.now().strftime("%Y%m%d")}.csv'
            }
        )
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500
