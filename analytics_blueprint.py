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
    cursor = db.cursor()

    try:
        if video_id:
            cursor.execute("""
                SELECT DATE(datetime(timestamp, 'unixepoch')) as date,
                       COUNT(*) as views
                FROM video_views
                WHERE agent_id = ? AND video_id = ? AND timestamp >= ?
                GROUP BY DATE(datetime(timestamp, 'unixepoch'))
                ORDER BY date
            """, (agent_id, video_id, start_timestamp))
        else:
            cursor.execute("""
                SELECT DATE(datetime(timestamp, 'unixepoch')) as date,
                       COUNT(*) as views
                FROM video_views v
                JOIN videos vd ON v.video_id = vd.id
                WHERE vd.agent_id = ? AND timestamp >= ?
                GROUP BY DATE(datetime(timestamp, 'unixepoch'))
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
            'success': True,
            'data': data,
            'period': period,
            'total_views': sum(item['views'] for item in data)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()


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
    cursor = db.cursor()

    try:
        cursor.execute("""
            SELECT
                v.title,
                v.id as video_id,
                COUNT(DISTINCT vw.id) as views,
                COUNT(DISTINCT l.id) as likes,
                COUNT(DISTINCT c.id) as comments,
                COUNT(DISTINCT s.id) as shares
            FROM videos v
            LEFT JOIN video_views vw ON v.id = vw.video_id AND vw.timestamp >= ?
            LEFT JOIN video_likes l ON v.id = l.video_id AND l.created_at >= ?
            LEFT JOIN video_comments c ON v.id = c.video_id AND c.created_at >= ?
            LEFT JOIN video_shares s ON v.id = s.video_id AND s.created_at >= ?
            WHERE v.agent_id = ?
            GROUP BY v.id, v.title
            ORDER BY views DESC
            LIMIT 20
        """, (start_timestamp, start_timestamp, start_timestamp, start_timestamp, agent_id))

        results = cursor.fetchall()

        data = []
        for row in results:
            engagement_rate = 0
            if row['views'] > 0:
                engagement_rate = ((row['likes'] + row['comments'] + row['shares']) / row['views']) * 100

            data.append({
                'video_id': row['video_id'],
                'title': row['title'],
                'views': row['views'],
                'likes': row['likes'],
                'comments': row['comments'],
                'shares': row['shares'],
                'engagement_rate': round(engagement_rate, 2)
            })

        return jsonify({
            'success': True,
            'data': data,
            'period': period
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()


@analytics_bp.route('/api/top-videos')
def api_top_videos():
    """
    Get top performing videos by view count.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    period = request.args.get('period', '30d')
    limit = int(request.args.get('limit', 10))

    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("""
            SELECT
                v.id,
                v.title,
                v.duration,
                v.created_at,
                COUNT(vw.id) as views,
                AVG(vw.watch_time) as avg_watch_time
            FROM videos v
            LEFT JOIN video_views vw ON v.id = vw.video_id AND vw.timestamp >= ?
            WHERE v.agent_id = ?
            GROUP BY v.id, v.title, v.duration, v.created_at
            ORDER BY views DESC
            LIMIT ?
        """, (start_timestamp, agent_id, limit))

        results = cursor.fetchall()

        data = []
        for row in results:
            retention_rate = 0
            if row['duration'] and row['avg_watch_time']:
                retention_rate = (row['avg_watch_time'] / row['duration']) * 100

            data.append({
                'video_id': row['id'],
                'title': row['title'],
                'views': row['views'],
                'duration': row['duration'],
                'avg_watch_time': row['avg_watch_time'],
                'retention_rate': round(retention_rate, 2),
                'created_at': row['created_at']
            })

        return jsonify({
            'success': True,
            'data': data,
            'period': period
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()


@analytics_bp.route('/api/audience')
def api_audience():
    """
    Get audience demographics and behavior data.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    period = request.args.get('period', '30d')
    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()
    cursor = db.cursor()

    try:
        # Get view times distribution
        cursor.execute("""
            SELECT
                CASE
                    WHEN CAST(strftime('%H', datetime(timestamp, 'unixepoch')) AS INTEGER) BETWEEN 0 AND 5 THEN 'Night (0-5)'
                    WHEN CAST(strftime('%H', datetime(timestamp, 'unixepoch')) AS INTEGER) BETWEEN 6 AND 11 THEN 'Morning (6-11)'
                    WHEN CAST(strftime('%H', datetime(timestamp, 'unixepoch')) AS INTEGER) BETWEEN 12 AND 17 THEN 'Afternoon (12-17)'
                    ELSE 'Evening (18-23)'
                END as time_period,
                COUNT(*) as views
            FROM video_views vw
            JOIN videos v ON vw.video_id = v.id
            WHERE v.agent_id = ? AND vw.timestamp >= ?
            GROUP BY time_period
            ORDER BY views DESC
        """, (agent_id, start_timestamp))

        time_distribution = []
        for row in cursor.fetchall():
            time_distribution.append({
                'period': row['time_period'],
                'views': row['views']
            })

        # Get device types (if tracked)
        cursor.execute("""
            SELECT
                COALESCE(device_type, 'Unknown') as device,
                COUNT(*) as views
            FROM video_views vw
            JOIN videos v ON vw.video_id = v.id
            WHERE v.agent_id = ? AND vw.timestamp >= ?
            GROUP BY device_type
            ORDER BY views DESC
        """, (agent_id, start_timestamp))

        device_distribution = []
        for row in cursor.fetchall():
            device_distribution.append({
                'device': row['device'],
                'views': row['views']
            })

        return jsonify({
            'success': True,
            'data': {
                'time_distribution': time_distribution,
                'device_distribution': device_distribution
            },
            'period': period
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()


@analytics_bp.route('/api/export')
def api_export():
    """
    Export analytics data as CSV.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    export_type = request.args.get('type', 'views')  # views, engagement, audience
    period = request.args.get('period', '30d')

    days = int(period.replace('d', ''))
    start_date = datetime.now() - timedelta(days=days)
    start_timestamp = start_date.timestamp()

    db = get_db()
    cursor = db.cursor()

    # Create CSV output
    output = io.StringIO()

    try:
        if export_type == 'views':
            cursor.execute("""
                SELECT
                    v.title as video_title,
                    DATE(datetime(vw.timestamp, 'unixepoch')) as view_date,
                    COUNT(*) as daily_views
                FROM video_views vw
                JOIN videos v ON vw.video_id = v.id
                WHERE v.agent_id = ? AND vw.timestamp >= ?
                GROUP BY v.id, v.title, DATE(datetime(vw.timestamp, 'unixepoch'))
                ORDER BY view_date DESC, daily_views DESC
            """, (agent_id, start_timestamp))

            fieldnames = ['video_title', 'view_date', 'daily_views']

        elif export_type == 'engagement':
            cursor.execute("""
                SELECT
                    v.title,
                    COUNT(DISTINCT vw.id) as views,
                    COUNT(DISTINCT l.id) as likes,
                    COUNT(DISTINCT c.id) as comments,
                    COUNT(DISTINCT s.id) as shares
                FROM videos v
                LEFT JOIN video_views vw ON v.id = vw.video_id AND vw.timestamp >= ?
                LEFT JOIN video_likes l ON v.id = l.video_id AND l.created_at >= ?
                LEFT JOIN video_comments c ON v.id = c.video_id AND c.created_at >= ?
                LEFT JOIN video_shares s ON v.id = s.video_id AND s.created_at >= ?
                WHERE v.agent_id = ?
                GROUP BY v.id, v.title
                ORDER BY views DESC
            """, (start_timestamp, start_timestamp, start_timestamp, start_timestamp, agent_id))

            fieldnames = ['title', 'views', 'likes', 'comments', 'shares']

        else:  # audience
            cursor.execute("""
                SELECT
                    DATE(datetime(vw.timestamp, 'unixepoch')) as date,
                    CAST(strftime('%H', datetime(vw.timestamp, 'unixepoch')) AS INTEGER) as hour,
                    COALESCE(vw.device_type, 'Unknown') as device,
                    COUNT(*) as views
                FROM video_views vw
                JOIN videos v ON vw.video_id = v.id
                WHERE v.agent_id = ? AND vw.timestamp >= ?
                GROUP BY date, hour, device
                ORDER BY date DESC, hour
            """, (agent_id, start_timestamp))

            fieldnames = ['date', 'hour', 'device', 'views']

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for row in cursor.fetchall():
            row_dict = {}
            for i, field in enumerate(fieldnames):
                row_dict[field] = row[i]
            writer.writerow(row_dict)

        output.seek(0)

        filename = f"bottube_analytics_{export_type}_{period}_{datetime.now().strftime('%Y%m%d')}.csv"

        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        output.close()
