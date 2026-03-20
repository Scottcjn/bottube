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
            cursor = db.execute(
                "SELECT COUNT(*) as views FROM video_views WHERE video_id = ? AND created_at >= ?",
                (video_id, start_timestamp)
            )
        else:
            cursor = db.execute(
                "SELECT COUNT(*) as views FROM video_views vv JOIN videos v ON vv.video_id = v.id WHERE v.agent_id = ? AND vv.created_at >= ?",
                (agent_id, start_timestamp)
            )

        total_views = cursor.fetchone()['views']

        # Get daily breakdown
        daily_views = []
        for i in range(days):
            day_start = start_date + timedelta(days=i)
            day_end = day_start + timedelta(days=1)

            if video_id:
                cursor = db.execute(
                    "SELECT COUNT(*) as views FROM video_views WHERE video_id = ? AND created_at >= ? AND created_at < ?",
                    (video_id, day_start.timestamp(), day_end.timestamp())
                )
            else:
                cursor = db.execute(
                    "SELECT COUNT(*) as views FROM video_views vv JOIN videos v ON vv.video_id = v.id WHERE v.agent_id = ? AND vv.created_at >= ? AND vv.created_at < ?",
                    (agent_id, day_start.timestamp(), day_end.timestamp())
                )

            day_views = cursor.fetchone()['views']
            daily_views.append({
                'date': day_start.strftime('%Y-%m-%d'),
                'views': day_views
            })

        return jsonify({
            'total_views': total_views,
            'daily_views': daily_views,
            'period': period
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/engagement')
def api_engagement():
    """
    Get engagement metrics (likes, comments, shares, retention)
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

    try:
        # Base query conditions
        if video_id:
            video_filter = "WHERE v.id = ?"
            params = [video_id]
        else:
            video_filter = "WHERE v.agent_id = ?"
            params = [agent_id]

        # Get engagement stats
        cursor = db.execute(f"""
            SELECT
                COUNT(DISTINCT l.id) as total_likes,
                COUNT(DISTINCT c.id) as total_comments,
                AVG(v.duration) as avg_duration,
                COUNT(DISTINCT v.id) as total_videos
            FROM videos v
            LEFT JOIN video_likes l ON v.id = l.video_id AND l.created_at >= ?
            LEFT JOIN video_comments c ON v.id = c.video_id AND c.created_at >= ?
            {video_filter}
        """, [start_timestamp, start_timestamp] + params)

        stats = cursor.fetchone()

        # Calculate engagement rate (likes + comments per view)
        cursor = db.execute(f"""
            SELECT COUNT(*) as total_views
            FROM video_views vv
            JOIN videos v ON vv.video_id = v.id
            {video_filter} AND vv.created_at >= ?
        """, params + [start_timestamp])

        total_views = cursor.fetchone()['total_views']
        engagement_rate = 0
        if total_views > 0:
            engagement_rate = (stats['total_likes'] + stats['total_comments']) / total_views * 100

        return jsonify({
            'total_likes': stats['total_likes'] or 0,
            'total_comments': stats['total_comments'] or 0,
            'engagement_rate': round(engagement_rate, 2),
            'avg_duration': round(stats['avg_duration'] or 0, 1),
            'total_videos': stats['total_videos'] or 0,
            'period': period
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/top-videos')
def api_top_videos():
    """
    Get top performing videos by views, likes, or engagement
    Query params:
    - sort_by: 'views', 'likes', 'comments', 'engagement' (default: views)
    - limit: number of results (default: 10, max: 50)
    - period: '7d', '30d', '90d', 'all' (default: 30d)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    sort_by = request.args.get('sort_by', 'views')
    limit = min(int(request.args.get('limit', 10)), 50)
    period = request.args.get('period', '30d')

    db = get_db()

    try:
        # Calculate date filter
        date_filter = ""
        params = [agent_id]

        if period != 'all':
            days = int(period.replace('d', ''))
            start_date = datetime.now() - timedelta(days=days)
            start_timestamp = start_date.timestamp()
            date_filter = "AND vv.created_at >= ?"
            params.append(start_timestamp)

        # Build query based on sort criteria
        if sort_by == 'views':
            order_by = "view_count DESC"
        elif sort_by == 'likes':
            order_by = "like_count DESC"
        elif sort_by == 'comments':
            order_by = "comment_count DESC"
        elif sort_by == 'engagement':
            order_by = "engagement_score DESC"
        else:
            order_by = "view_count DESC"

        cursor = db.execute(f"""
            SELECT
                v.id,
                v.title,
                v.thumbnail_url,
                v.duration,
                v.created_at,
                COUNT(DISTINCT vv.id) as view_count,
                COUNT(DISTINCT l.id) as like_count,
                COUNT(DISTINCT c.id) as comment_count,
                (COUNT(DISTINCT l.id) + COUNT(DISTINCT c.id)) as engagement_score
            FROM videos v
            LEFT JOIN video_views vv ON v.id = vv.video_id {date_filter}
            LEFT JOIN video_likes l ON v.id = l.video_id
            LEFT JOIN video_comments c ON v.id = c.video_id
            WHERE v.agent_id = ?
            GROUP BY v.id, v.title, v.thumbnail_url, v.duration, v.created_at
            ORDER BY {order_by}
            LIMIT ?
        """, params + [limit])

        videos = []
        for row in cursor.fetchall():
            videos.append({
                'id': row['id'],
                'title': row['title'],
                'thumbnail_url': row['thumbnail_url'],
                'duration': row['duration'],
                'created_at': row['created_at'],
                'view_count': row['view_count'],
                'like_count': row['like_count'],
                'comment_count': row['comment_count'],
                'engagement_score': row['engagement_score']
            })

        return jsonify({
            'videos': videos,
            'sort_by': sort_by,
            'period': period,
            'total_results': len(videos)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/api/audience')
def api_audience():
    """
    Get audience breakdown and demographics
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
        # Get unique viewers and their activity patterns
        cursor = db.execute("""
            SELECT
                vv.ip_address,
                vv.user_agent,
                COUNT(*) as view_count,
                COUNT(DISTINCT vv.video_id) as unique_videos,
                MIN(vv.created_at) as first_view,
                MAX(vv.created_at) as last_view
            FROM video_views vv
            JOIN videos v ON vv.video_id = v.id
            WHERE v.agent_id = ? AND vv.created_at >= ?
            GROUP BY vv.ip_address, vv.user_agent
        """, (agent_id, start_timestamp))

        viewers = cursor.fetchall()

        # Analyze viewer behavior
        new_viewers = 0
        returning_viewers = 0
        total_unique_viewers = len(viewers)

        for viewer in viewers:
            # Check if viewer existed before this period
            cursor = db.execute("""
                SELECT COUNT(*) as prior_views
                FROM video_views vv
                JOIN videos v ON vv.video_id = v.id
                WHERE v.agent_id = ? AND vv.ip_address = ? AND vv.user_agent = ? AND vv.created_at < ?
            """, (agent_id, viewer['ip_address'], viewer['user_agent'], start_timestamp))

            prior_views = cursor.fetchone()['prior_views']
            if prior_views > 0:
                returning_viewers += 1
            else:
                new_viewers += 1

        # Get hourly view distribution
        cursor = db.execute("""
            SELECT
                strftime('%H', datetime(vv.created_at, 'unixepoch')) as hour,
                COUNT(*) as views
            FROM video_views vv
            JOIN videos v ON vv.video_id = v.id
            WHERE v.agent_id = ? AND vv.created_at >= ?
            GROUP BY hour
            ORDER BY hour
        """, (agent_id, start_timestamp))

        hourly_views = {}
        for row in cursor.fetchall():
            hourly_views[int(row['hour'])] = row['views']

        return jsonify({
            'total_unique_viewers': total_unique_viewers,
            'new_viewers': new_viewers,
            'returning_viewers': returning_viewers,
            'returning_viewer_rate': round((returning_viewers / total_unique_viewers * 100) if total_unique_viewers > 0 else 0, 1),
            'hourly_distribution': hourly_views,
            'period': period
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/export/csv')
def export_csv():
    """
    Export analytics data as CSV
    Query params:
    - type: 'views', 'engagement', 'videos', 'audience' (required)
    - period: '7d', '30d', '90d' (default: 30d)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    export_type = request.args.get('type')
    if not export_type:
        return jsonify({"error": "type parameter required"}), 400

    period = request.args.get('period', '30d')

    try:
        output = io.StringIO()
        writer = csv.writer(output)

        if export_type == 'views':
            # Export daily view data
            response = api_views()
            data = json.loads(response.data)

            writer.writerow(['Date', 'Views'])
            for day in data['daily_views']:
                writer.writerow([day['date'], day['views']])

            filename = f'views_{period}.csv'

        elif export_type == 'videos':
            # Export top videos data
            request.args = request.args.copy()
            request.args['limit'] = '100'
            response = api_top_videos()
            data = json.loads(response.data)

            writer.writerow(['Title', 'Views', 'Likes', 'Comments', 'Engagement Score', 'Duration', 'Created At'])
            for video in data['videos']:
                writer.writerow([
                    video['title'], video['view_count'], video['like_count'],
                    video['comment_count'], video['engagement_score'],
                    video['duration'], video['created_at']
                ])

            filename = f'videos_{period}.csv'

        else:
            return jsonify({"error": "Invalid export type"}), 400

        output.seek(0)

        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
