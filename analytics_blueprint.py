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
    if video_id:
        query = """
        SELECT DATE(datetime(timestamp, 'unixepoch')) as date,
               COUNT(*) as views
        FROM video_views
        WHERE video_id = ? AND creator_id = ? AND timestamp >= ?
        GROUP BY DATE(datetime(timestamp, 'unixepoch'))
        ORDER BY date
        """
        cursor = db.execute(query, (video_id, agent_id, start_timestamp))
    else:
        query = """
        SELECT DATE(datetime(timestamp, 'unixepoch')) as date,
               COUNT(*) as views
        FROM video_views v
        JOIN videos vd ON v.video_id = vd.id
        WHERE vd.creator_id = ? AND v.timestamp >= ?
        GROUP BY DATE(datetime(timestamp, 'unixepoch'))
        ORDER BY date
        """
        cursor = db.execute(query, (agent_id, start_timestamp))

    results = cursor.fetchall()

    # Format response
    trend_data = []
    for row in results:
        trend_data.append({
            "date": row["date"],
            "views": row["views"]
        })

    return jsonify({
        "success": True,
        "period": period,
        "video_id": video_id,
        "data": trend_data
    })


@analytics_bp.route('/api/engagement')
def api_engagement():
    """
    Get engagement metrics (likes, comments, shares) for creator's videos.
    Query params:
    - period: '7d', '30d', '90d' (default: 30d)
    - video_id: specific video filter (optional)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    period = request.args.get('period', '30d')
    video_id = request.args.get('video_id')

    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()

    # Get engagement data
    if video_id:
        # Single video engagement
        query = """
        SELECT
            COUNT(CASE WHEN v.vote_type = 1 THEN 1 END) as likes,
            COUNT(CASE WHEN v.vote_type = -1 THEN 1 END) as dislikes,
            COUNT(c.id) as comments
        FROM videos vd
        LEFT JOIN votes v ON vd.id = v.video_id AND v.timestamp >= ?
        LEFT JOIN comments c ON vd.id = c.video_id AND c.timestamp >= ?
        WHERE vd.id = ? AND vd.creator_id = ?
        """
        cursor = db.execute(query, (start_timestamp, start_timestamp, video_id, agent_id))
    else:
        # All videos engagement
        query = """
        SELECT
            COUNT(CASE WHEN v.vote_type = 1 THEN 1 END) as likes,
            COUNT(CASE WHEN v.vote_type = -1 THEN 1 END) as dislikes,
            COUNT(c.id) as comments
        FROM videos vd
        LEFT JOIN votes v ON vd.id = v.video_id AND v.timestamp >= ?
        LEFT JOIN comments c ON vd.id = c.video_id AND c.timestamp >= ?
        WHERE vd.creator_id = ?
        """
        cursor = db.execute(query, (start_timestamp, start_timestamp, agent_id))

    result = cursor.fetchone()

    return jsonify({
        "success": True,
        "period": period,
        "video_id": video_id,
        "data": {
            "likes": result["likes"] or 0,
            "dislikes": result["dislikes"] or 0,
            "comments": result["comments"] or 0,
            "engagement_rate": 0  # TODO: calculate based on views
        }
    })


@analytics_bp.route('/api/top-videos')
def api_top_videos():
    """
    Get top performing videos for a creator.
    Query params:
    - period: '7d', '30d', '90d' (default: 30d)
    - limit: number of videos to return (default: 10)
    - sort_by: 'views', 'likes', 'comments' (default: views)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    period = request.args.get('period', '30d')
    limit = int(request.args.get('limit', 10))
    sort_by = request.args.get('sort_by', 'views')

    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()

    # Build query based on sort criteria
    if sort_by == 'likes':
        order_clause = "likes DESC"
    elif sort_by == 'comments':
        order_clause = "comments DESC"
    else:
        order_clause = "views DESC"

    query = f"""
    SELECT
        v.id,
        v.title,
        v.description,
        v.thumbnail_url,
        v.upload_timestamp,
        COUNT(DISTINCT vw.id) as views,
        COUNT(DISTINCT CASE WHEN vo.vote_type = 1 THEN vo.id END) as likes,
        COUNT(DISTINCT CASE WHEN vo.vote_type = -1 THEN vo.id END) as dislikes,
        COUNT(DISTINCT c.id) as comments
    FROM videos v
    LEFT JOIN video_views vw ON v.id = vw.video_id AND vw.timestamp >= ?
    LEFT JOIN votes vo ON v.id = vo.video_id AND vo.timestamp >= ?
    LEFT JOIN comments c ON v.id = c.video_id AND c.timestamp >= ?
    WHERE v.creator_id = ?
    GROUP BY v.id, v.title, v.description, v.thumbnail_url, v.upload_timestamp
    ORDER BY {order_clause}
    LIMIT ?
    """

    cursor = db.execute(query, (start_timestamp, start_timestamp, start_timestamp, agent_id, limit))
    results = cursor.fetchall()

    videos = []
    for row in results:
        videos.append({
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "thumbnail_url": row["thumbnail_url"],
            "upload_date": datetime.fromtimestamp(row["upload_timestamp"]).isoformat(),
            "views": row["views"] or 0,
            "likes": row["likes"] or 0,
            "dislikes": row["dislikes"] or 0,
            "comments": row["comments"] or 0
        })

    return jsonify({
        "success": True,
        "period": period,
        "sort_by": sort_by,
        "data": videos
    })


@analytics_bp.route('/api/audience')
def api_audience():
    """
    Get audience breakdown and demographics.
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

    # Get unique viewers
    query = """
    SELECT COUNT(DISTINCT vw.viewer_id) as unique_viewers,
           COUNT(vw.id) as total_views
    FROM video_views vw
    JOIN videos v ON vw.video_id = v.id
    WHERE v.creator_id = ? AND vw.timestamp >= ?
    """
    cursor = db.execute(query, (agent_id, start_timestamp))
    audience_stats = cursor.fetchone()

    # Get top viewer countries (if we have location data)
    countries_query = """
    SELECT vw.country, COUNT(*) as views
    FROM video_views vw
    JOIN videos v ON vw.video_id = v.id
    WHERE v.creator_id = ? AND vw.timestamp >= ? AND vw.country IS NOT NULL
    GROUP BY vw.country
    ORDER BY views DESC
    LIMIT 10
    """
    cursor = db.execute(countries_query, (agent_id, start_timestamp))
    countries = [{
        "country": row["country"],
        "views": row["views"]
    } for row in cursor.fetchall()]

    return jsonify({
        "success": True,
        "period": period,
        "data": {
            "unique_viewers": audience_stats["unique_viewers"] or 0,
            "total_views": audience_stats["total_views"] or 0,
            "return_rate": 0,  # TODO: calculate return viewer rate
            "top_countries": countries
        }
    })


@analytics_bp.route('/api/export')
def export_analytics():
    """
    Export analytics data as CSV.
    Query params:
    - type: 'views', 'engagement', 'videos', 'audience'
    - period: '7d', '30d', '90d' (default: 30d)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    export_type = request.args.get('type', 'views')
    period = request.args.get('period', '30d')

    # Create CSV content based on type
    output = io.StringIO()

    if export_type == 'videos':
        # Export top videos data
        # Reuse the top-videos API logic
        from urllib.parse import urlencode
        import requests

        # For simplicity, we'll create the data directly here
        days = int(period.replace('d', ''))
        start_date = datetime.now() - timedelta(days=days)
        start_timestamp = start_date.timestamp()

        db = get_db()
        query = """
        SELECT
            v.id, v.title, v.upload_timestamp,
            COUNT(DISTINCT vw.id) as views,
            COUNT(DISTINCT CASE WHEN vo.vote_type = 1 THEN vo.id END) as likes,
            COUNT(DISTINCT CASE WHEN vo.vote_type = -1 THEN vo.id END) as dislikes,
            COUNT(DISTINCT c.id) as comments
        FROM videos v
        LEFT JOIN video_views vw ON v.id = vw.video_id AND vw.timestamp >= ?
        LEFT JOIN votes vo ON v.id = vo.video_id AND vo.timestamp >= ?
        LEFT JOIN comments c ON v.id = c.video_id AND c.timestamp >= ?
        WHERE v.creator_id = ?
        GROUP BY v.id, v.title, v.upload_timestamp
        ORDER BY views DESC
        """

        cursor = db.execute(query, (start_timestamp, start_timestamp, start_timestamp, agent_id))
        results = cursor.fetchall()

        writer = csv.writer(output)
        writer.writerow(['Video ID', 'Title', 'Upload Date', 'Views', 'Likes', 'Dislikes', 'Comments'])

        for row in results:
            writer.writerow([
                row['id'],
                row['title'],
                datetime.fromtimestamp(row['upload_timestamp']).strftime('%Y-%m-%d'),
                row['views'] or 0,
                row['likes'] or 0,
                row['dislikes'] or 0,
                row['comments'] or 0
            ])

        filename = f'bottube_videos_{period}_{datetime.now().strftime("%Y%m%d")}.csv'

    else:
        # Default to views export
        days = int(period.replace('d', ''))
        start_date = datetime.now() - timedelta(days=days)
        start_timestamp = start_date.timestamp()

        db = get_db()
        query = """
        SELECT DATE(datetime(timestamp, 'unixepoch')) as date,
               COUNT(*) as views
        FROM video_views v
        JOIN videos vd ON v.video_id = vd.id
        WHERE vd.creator_id = ? AND v.timestamp >= ?
        GROUP BY DATE(datetime(timestamp, 'unixepoch'))
        ORDER BY date
        """

        cursor = db.execute(query, (agent_id, start_timestamp))
        results = cursor.fetchall()

        writer = csv.writer(output)
        writer.writerow(['Date', 'Views'])

        for row in results:
            writer.writerow([row['date'], row['views']])

        filename = f'bottube_views_{period}_{datetime.now().strftime("%Y%m%d")}.csv'

    # Return CSV file
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )
