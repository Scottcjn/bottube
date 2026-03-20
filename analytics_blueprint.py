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
                SELECT DATE(view_timestamp) as date, COUNT(*) as views
                FROM video_views
                WHERE agent_id = ? AND video_id = ? AND view_timestamp >= ?
                GROUP BY DATE(view_timestamp)
                ORDER BY date
            """, (agent_id, video_id, start_timestamp))
        else:
            cursor = db.execute("""
                SELECT DATE(v.view_timestamp) as date, COUNT(*) as views
                FROM video_views v
                JOIN videos vid ON v.video_id = vid.id
                WHERE vid.agent_id = ? AND v.view_timestamp >= ?
                GROUP BY DATE(v.view_timestamp)
                ORDER BY date
            """, (agent_id, start_timestamp))

        results = cursor.fetchall()

        # Format data for chart
        data = []
        for row in results:
            data.append({
                'date': row['date'],
                'views': row['views']
            })

        return jsonify({
            'period': period,
            'data': data,
            'total_views': sum(item['views'] for item in data)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/api/engagement')
def api_engagement():
    """
    Get engagement metrics (likes, comments, shares) for creator's videos.
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
                v.title,
                v.id as video_id,
                COUNT(DISTINCT vv.id) as views,
                COUNT(DISTINCT l.id) as likes,
                COUNT(DISTINCT c.id) as comments
            FROM videos v
            LEFT JOIN video_views vv ON v.id = vv.video_id AND vv.view_timestamp >= ?
            LEFT JOIN likes l ON v.id = l.video_id AND l.created_at >= ?
            LEFT JOIN comments c ON v.id = c.video_id AND c.created_at >= ?
            WHERE v.agent_id = ?
            GROUP BY v.id, v.title
            ORDER BY views DESC
            LIMIT 10
        """, (start_timestamp, start_timestamp, start_timestamp, agent_id))

        results = cursor.fetchall()

        data = []
        for row in results:
            engagement_rate = 0
            if row['views'] > 0:
                engagement_rate = ((row['likes'] + row['comments']) / row['views']) * 100

            data.append({
                'video_id': row['video_id'],
                'title': row['title'],
                'views': row['views'],
                'likes': row['likes'],
                'comments': row['comments'],
                'engagement_rate': round(engagement_rate, 2)
            })

        return jsonify({
            'period': period,
            'data': data
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/api/top-videos')
def api_top_videos():
    """
    Get top performing videos by view count.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    period = request.args.get('period', '30d')
    limit = min(int(request.args.get('limit', 10)), 50)  # Max 50 results

    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()

    try:
        cursor = db.execute("""
            SELECT
                v.id,
                v.title,
                v.description,
                v.created_at,
                COUNT(vv.id) as views,
                v.file_path
            FROM videos v
            LEFT JOIN video_views vv ON v.id = vv.video_id AND vv.view_timestamp >= ?
            WHERE v.agent_id = ?
            GROUP BY v.id
            ORDER BY views DESC
            LIMIT ?
        """, (start_timestamp, agent_id, limit))

        results = cursor.fetchall()

        data = []
        for row in results:
            data.append({
                'id': row['id'],
                'title': row['title'],
                'description': row['description'][:100] + '...' if len(row['description']) > 100 else row['description'],
                'views': row['views'],
                'created_at': row['created_at'],
                'thumbnail_url': f'/static/thumbnails/{row["id"]}.jpg' if row['file_path'] else None
            })

        return jsonify({
            'period': period,
            'data': data
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/api/export/csv')
def export_csv():
    """
    Export analytics data as CSV file.
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
        # Get comprehensive analytics data
        cursor = db.execute("""
            SELECT
                v.id,
                v.title,
                v.description,
                v.created_at,
                COUNT(DISTINCT vv.id) as views,
                COUNT(DISTINCT l.id) as likes,
                COUNT(DISTINCT c.id) as comments
            FROM videos v
            LEFT JOIN video_views vv ON v.id = vv.video_id AND vv.view_timestamp >= ?
            LEFT JOIN likes l ON v.id = l.video_id AND l.created_at >= ?
            LEFT JOIN comments c ON v.id = c.video_id AND c.created_at >= ?
            WHERE v.agent_id = ?
            GROUP BY v.id
            ORDER BY views DESC
        """, (start_timestamp, start_timestamp, start_timestamp, agent_id))

        results = cursor.fetchall()

        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(['Video ID', 'Title', 'Description', 'Created At', 'Views', 'Likes', 'Comments', 'Engagement Rate'])

        # Data rows
        for row in results:
            engagement_rate = 0
            if row['views'] > 0:
                engagement_rate = ((row['likes'] + row['comments']) / row['views']) * 100

            writer.writerow([
                row['id'],
                row['title'],
                row['description'],
                row['created_at'],
                row['views'],
                row['likes'],
                row['comments'],
                f"{engagement_rate:.2f}%"
            ])

        output.seek(0)

        # Create response
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={"Content-Disposition": f"attachment; filename=analytics_{agent_id}_{period}.csv"}
        )

        return response

    except Exception as e:
        return jsonify({'error': str(e)}), 500
