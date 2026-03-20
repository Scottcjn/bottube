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

    # Get total views and daily breakdown
    if video_id:
        query = """
            SELECT DATE(created_at) as date, COUNT(*) as views
            FROM video_views
            WHERE agent_id = ? AND video_id = ? AND created_at >= ?
            GROUP BY DATE(created_at)
            ORDER BY date
        """
        rows = db.execute(query, (agent_id, video_id, start_timestamp)).fetchall()
    else:
        query = """
            SELECT DATE(created_at) as date, COUNT(*) as views
            FROM video_views
            WHERE agent_id = ? AND created_at >= ?
            GROUP BY DATE(created_at)
            ORDER BY date
        """
        rows = db.execute(query, (agent_id, start_timestamp)).fetchall()

    # Format response
    daily_views = []
    total_views = 0

    for row in rows:
        daily_views.append({
            'date': row['date'],
            'views': row['views']
        })
        total_views += row['views']

    return jsonify({
        'period': period,
        'total_views': total_views,
        'daily_views': daily_views,
        'video_id': video_id
    })


@analytics_bp.route('/api/engagement')
@login_required
def api_engagement():
    """
    Get engagement metrics (likes, comments, shares, etc.)
    Query params:
    - period: '7d', '30d', '90d' (default: 30d)
    - video_id: specific video filter (optional)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id') or session.get('agent_id')
    period = request.args.get('period', '30d')
    video_id = request.args.get('video_id')

    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()

    # Get engagement data
    base_query = """
        SELECT
            COUNT(CASE WHEN action = 'like' THEN 1 END) as likes,
            COUNT(CASE WHEN action = 'comment' THEN 1 END) as comments,
            COUNT(CASE WHEN action = 'share' THEN 1 END) as shares,
            COUNT(*) as total_interactions
        FROM video_interactions
        WHERE agent_id = ? AND created_at >= ?
    """

    params = [agent_id, start_timestamp]
    if video_id:
        base_query += " AND video_id = ?"
        params.append(video_id)

    row = db.execute(base_query, params).fetchone()

    return jsonify({
        'period': period,
        'likes': row['likes'] or 0,
        'comments': row['comments'] or 0,
        'shares': row['shares'] or 0,
        'total_interactions': row['total_interactions'] or 0,
        'video_id': video_id
    })


@analytics_bp.route('/api/top-videos')
@login_required
def api_top_videos():
    """
    Get top performing videos by view count.
    Query params:
    - limit: number of results (default: 10, max: 100)
    - period: '7d', '30d', '90d', 'all' (default: 30d)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id') or session.get('agent_id')
    limit = min(int(request.args.get('limit', 10)), 100)
    period = request.args.get('period', '30d')

    db = get_db()

    if period == 'all':
        query = """
            SELECT
                v.video_id,
                v.title,
                v.description,
                v.created_at,
                COUNT(vw.id) as view_count,
                COUNT(vi.id) as interaction_count
            FROM videos v
            LEFT JOIN video_views vw ON v.video_id = vw.video_id
            LEFT JOIN video_interactions vi ON v.video_id = vi.video_id
            WHERE v.agent_id = ?
            GROUP BY v.video_id
            ORDER BY view_count DESC
            LIMIT ?
        """
        params = [agent_id, limit]
    else:
        days = int(period.replace('d', ''))
        start_date = datetime.now() - timedelta(days=days)
        start_timestamp = start_date.timestamp()

        query = """
            SELECT
                v.video_id,
                v.title,
                v.description,
                v.created_at,
                COUNT(vw.id) as view_count,
                COUNT(vi.id) as interaction_count
            FROM videos v
            LEFT JOIN video_views vw ON v.video_id = vw.video_id AND vw.created_at >= ?
            LEFT JOIN video_interactions vi ON v.video_id = vi.video_id AND vi.created_at >= ?
            WHERE v.agent_id = ?
            GROUP BY v.video_id
            ORDER BY view_count DESC
            LIMIT ?
        """
        params = [start_timestamp, start_timestamp, agent_id, limit]

    rows = db.execute(query, params).fetchall()

    videos = []
    for row in rows:
        videos.append({
            'video_id': row['video_id'],
            'title': row['title'],
            'description': row['description'][:200] + '...' if len(row['description']) > 200 else row['description'],
            'created_at': row['created_at'],
            'view_count': row['view_count'],
            'interaction_count': row['interaction_count']
        })

    return jsonify({
        'period': period,
        'limit': limit,
        'videos': videos
    })


@analytics_bp.route('/api/audience')
@login_required
def api_audience():
    """
    Get audience breakdown and demographics.
    Query params:
    - period: '7d', '30d', '90d' (default: 30d)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id') or session.get('agent_id')
    period = request.args.get('period', '30d')

    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()

    # Get unique viewers
    unique_viewers_query = """
        SELECT COUNT(DISTINCT viewer_id) as unique_viewers
        FROM video_views
        WHERE agent_id = ? AND created_at >= ?
    """
    unique_viewers = db.execute(unique_viewers_query, (agent_id, start_timestamp)).fetchone()['unique_viewers']

    # Get returning vs new viewers (simplified - assumes viewer_id tracks this)
    viewer_breakdown_query = """
        SELECT
            viewer_id,
            MIN(created_at) as first_view,
            COUNT(*) as view_count
        FROM video_views
        WHERE agent_id = ? AND created_at >= ?
        GROUP BY viewer_id
    """
    viewer_rows = db.execute(viewer_breakdown_query, (agent_id, start_timestamp)).fetchall()

    new_viewers = 0
    returning_viewers = 0

    for row in viewer_rows:
        if row['first_view'] >= start_timestamp:
            new_viewers += 1
        else:
            returning_viewers += 1

    return jsonify({
        'period': period,
        'unique_viewers': unique_viewers or 0,
        'new_viewers': new_viewers,
        'returning_viewers': returning_viewers,
        'retention_rate': round((returning_viewers / max(unique_viewers, 1)) * 100, 2)
    })


@analytics_bp.route('/api/export')
@login_required
def api_export():
    """
    Export analytics data as CSV.
    Query params:
    - type: 'views', 'engagement', 'videos', 'audience' (default: views)
    - period: '7d', '30d', '90d', 'all' (default: 30d)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id') or session.get('agent_id')
    export_type = request.args.get('type', 'views')
    period = request.args.get('period', '30d')

    db = get_db()

    # Create CSV content based on export type
    output = io.StringIO()

    if export_type == 'views':
        writer = csv.writer(output)
        writer.writerow(['Date', 'Views', 'Video ID', 'Video Title'])

        if period == 'all':
            query = """
                SELECT
                    DATE(vw.created_at) as date,
                    COUNT(*) as views,
                    v.video_id,
                    v.title
                FROM video_views vw
                JOIN videos v ON vw.video_id = v.video_id
                WHERE vw.agent_id = ?
                GROUP BY DATE(vw.created_at), v.video_id
                ORDER BY date DESC, views DESC
            """
            params = [agent_id]
        else:
            days = int(period.replace('d', ''))
            start_date = datetime.now() - timedelta(days=days)
            start_timestamp = start_date.timestamp()

            query = """
                SELECT
                    DATE(vw.created_at) as date,
                    COUNT(*) as views,
                    v.video_id,
                    v.title
                FROM video_views vw
                JOIN videos v ON vw.video_id = v.video_id
                WHERE vw.agent_id = ? AND vw.created_at >= ?
                GROUP BY DATE(vw.created_at), v.video_id
                ORDER BY date DESC, views DESC
            """
            params = [agent_id, start_timestamp]

        rows = db.execute(query, params).fetchall()
        for row in rows:
            writer.writerow([row['date'], row['views'], row['video_id'], row['title']])

    elif export_type == 'engagement':
        writer = csv.writer(output)
        writer.writerow(['Date', 'Video ID', 'Action', 'Count'])

        if period == 'all':
            query = """
                SELECT
                    DATE(created_at) as date,
                    video_id,
                    action,
                    COUNT(*) as count
                FROM video_interactions
                WHERE agent_id = ?
                GROUP BY DATE(created_at), video_id, action
                ORDER BY date DESC, count DESC
            """
            params = [agent_id]
        else:
            days = int(period.replace('d', ''))
            start_date = datetime.now() - timedelta(days=days)
            start_timestamp = start_date.timestamp()

            query = """
                SELECT
                    DATE(created_at) as date,
                    video_id,
                    action,
                    COUNT(*) as count
                FROM video_interactions
                WHERE agent_id = ? AND created_at >= ?
                GROUP BY DATE(created_at), video_id, action
                ORDER BY date DESC, count DESC
            """
            params = [agent_id, start_timestamp]

        rows = db.execute(query, params).fetchall()
        for row in rows:
            writer.writerow([row['date'], row['video_id'], row['action'], row['count']])

    # Create response
    csv_content = output.getvalue()
    output.close()

    response = Response(
        csv_content,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=analytics_{export_type}_{period}.csv'
        }
    )

    return response
