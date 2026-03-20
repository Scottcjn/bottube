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
        if video_id:
            cursor = db.execute("""
                SELECT DATE(timestamp, 'unixepoch') as date, COUNT(*) as views
                FROM video_views
                WHERE video_id = ? AND timestamp >= ?
                GROUP BY DATE(timestamp, 'unixepoch')
                ORDER BY date
            """, (video_id, start_timestamp))
        else:
            cursor = db.execute("""
                SELECT DATE(v.timestamp, 'unixepoch') as date, COUNT(*) as views
                FROM video_views v
                JOIN videos vi ON v.video_id = vi.id
                WHERE vi.agent_id = ? AND v.timestamp >= ?
                GROUP BY DATE(v.timestamp, 'unixepoch')
                ORDER BY date
            """, (agent_id, start_timestamp))

        results = cursor.fetchall()

        # Format data for chart
        chart_data = {
            'labels': [row['date'] for row in results],
            'datasets': [{
                'label': 'Daily Views',
                'data': [row['views'] for row in results],
                'borderColor': 'rgb(75, 192, 192)',
                'tension': 0.1
            }]
        }

        return jsonify(chart_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/engagement')
def api_engagement():
    """
    Get engagement metrics (likes, comments, shares).
    Query params:
    - period: '7d', '30d', '90d' (default: 30d)
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
        # Get engagement data
        cursor = db.execute("""
            SELECT
                COUNT(DISTINCT l.id) as likes,
                COUNT(DISTINCT c.id) as comments,
                COUNT(DISTINCT s.id) as shares
            FROM videos v
            LEFT JOIN likes l ON v.id = l.video_id AND l.timestamp >= ?
            LEFT JOIN comments c ON v.id = c.video_id AND c.timestamp >= ?
            LEFT JOIN shares s ON v.id = s.video_id AND s.timestamp >= ?
            WHERE v.agent_id = ?
        """, (start_timestamp, start_timestamp, start_timestamp, agent_id))

        result = cursor.fetchone()

        engagement_data = {
            'likes': result['likes'] or 0,
            'comments': result['comments'] or 0,
            'shares': result['shares'] or 0
        }

        return jsonify(engagement_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/top-videos')
def api_top_videos():
    """
    Get top performing videos by view count.
    Query params:
    - limit: number of videos to return (default: 10)
    - period: '7d', '30d', '90d', 'all' (default: 30d)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    limit = int(request.args.get('limit', 10))
    period = request.args.get('period', '30d')

    db = get_db()

    try:
        if period == 'all':
            cursor = db.execute("""
                SELECT v.id, v.title, v.thumbnail_url, COUNT(vw.id) as view_count
                FROM videos v
                LEFT JOIN video_views vw ON v.id = vw.video_id
                WHERE v.agent_id = ?
                GROUP BY v.id, v.title, v.thumbnail_url
                ORDER BY view_count DESC
                LIMIT ?
            """, (agent_id, limit))
        else:
            days = int(period.replace('d', ''))
            start_date = datetime.now() - timedelta(days=days)
            start_timestamp = start_date.timestamp()

            cursor = db.execute("""
                SELECT v.id, v.title, v.thumbnail_url, COUNT(vw.id) as view_count
                FROM videos v
                LEFT JOIN video_views vw ON v.id = vw.video_id AND vw.timestamp >= ?
                WHERE v.agent_id = ?
                GROUP BY v.id, v.title, v.thumbnail_url
                ORDER BY view_count DESC
                LIMIT ?
            """, (start_timestamp, agent_id, limit))

        results = cursor.fetchall()

        top_videos = [{
            'id': row['id'],
            'title': row['title'],
            'thumbnail_url': row['thumbnail_url'],
            'view_count': row['view_count'] or 0
        } for row in results]

        return jsonify(top_videos)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/audience')
def api_audience():
    """
    Get audience breakdown data.
    Returns demographics and viewing patterns.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    db = get_db()

    try:
        # Get viewer demographics (if available)
        cursor = db.execute("""
            SELECT
                u.country,
                COUNT(DISTINCT vw.user_id) as unique_viewers
            FROM video_views vw
            JOIN videos v ON vw.video_id = v.id
            LEFT JOIN users u ON vw.user_id = u.id
            WHERE v.agent_id = ?
            GROUP BY u.country
            ORDER BY unique_viewers DESC
            LIMIT 10
        """, (agent_id,))

        country_results = cursor.fetchall()

        # Get viewing time patterns
        cursor = db.execute("""
            SELECT
                strftime('%H', timestamp, 'unixepoch') as hour,
                COUNT(*) as views
            FROM video_views vw
            JOIN videos v ON vw.video_id = v.id
            WHERE v.agent_id = ?
            GROUP BY hour
            ORDER BY hour
        """, (agent_id,))

        hour_results = cursor.fetchall()

        audience_data = {
            'countries': [{
                'country': row['country'] or 'Unknown',
                'viewers': row['unique_viewers']
            } for row in country_results],
            'viewing_hours': [{
                'hour': int(row['hour']),
                'views': row['views']
            } for row in hour_results]
        }

        return jsonify(audience_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/export')
def api_export():
    """
    Export analytics data as CSV.
    Query params:
    - type: 'views', 'engagement', 'videos' (default: views)
    - period: '7d', '30d', '90d' (default: 30d)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    export_type = request.args.get('type', 'views')
    period = request.args.get('period', '30d')

    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()

    try:
        output = io.StringIO()
        writer = csv.writer(output)

        if export_type == 'views':
            cursor = db.execute("""
                SELECT DATE(v.timestamp, 'unixepoch') as date, COUNT(*) as views
                FROM video_views v
                JOIN videos vi ON v.video_id = vi.id
                WHERE vi.agent_id = ? AND v.timestamp >= ?
                GROUP BY DATE(v.timestamp, 'unixepoch')
                ORDER BY date
            """, (agent_id, start_timestamp))

            writer.writerow(['Date', 'Views'])
            for row in cursor:
                writer.writerow([row['date'], row['views']])

        elif export_type == 'videos':
            cursor = db.execute("""
                SELECT v.title, v.upload_date, COUNT(vw.id) as view_count
                FROM videos v
                LEFT JOIN video_views vw ON v.id = vw.video_id
                WHERE v.agent_id = ?
                GROUP BY v.id, v.title, v.upload_date
                ORDER BY view_count DESC
            """, (agent_id,))

            writer.writerow(['Title', 'Upload Date', 'Views'])
            for row in cursor:
                writer.writerow([row['title'], row['upload_date'], row['view_count'] or 0])

        output.seek(0)

        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={"Content-disposition": f"attachment; filename=analytics_{export_type}_{period}.csv"}
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
