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
from flask import Blueprint, render_template, jsonify, request, g, Response
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
    
    # Get total views in period
    if video_id:
        total_views = db.execute(
            """SELECT COUNT(*) FROM views 
               WHERE video_id = ? AND created_at >= ?""",
            (video_id, start_timestamp)
        ).fetchone()[0]
        
        # Daily breakdown
        daily = db.execute(
            """SELECT date(created_at, 'unixepoch') as day, COUNT(*) as count
               FROM views 
               WHERE video_id = ? AND created_at >= ?
               GROUP BY day ORDER BY day""",
            (video_id, start_timestamp)
        ).fetchall()
    else:
        # Get all videos by this agent
        videos = db.execute(
            "SELECT id FROM videos WHERE agent_id = ?",
            (agent_id,)
        ).fetchall()
        video_ids = [v[0] for v in videos]
        
        if not video_ids:
            return jsonify({
                "period": period,
                "total_views": 0,
                "daily_breakdown": [],
                "videos_count": 0
            })
        
        placeholders = ','.join('?' * len(video_ids))
        total_views = db.execute(
            f"""SELECT COUNT(*) FROM views 
                WHERE video_id IN ({placeholders}) AND created_at >= ?""",
            tuple(video_ids) + (start_timestamp,)
        ).fetchone()[0]
        
        daily = db.execute(
            f"""SELECT date(created_at, 'unixepoch') as day, COUNT(*) as count
                FROM views 
                WHERE video_id IN ({placeholders}) AND created_at >= ?
                GROUP BY day ORDER BY day""",
            tuple(video_ids) + (start_timestamp,)
        ).fetchall()
    
    return jsonify({
        "period": period,
        "total_views": total_views,
        "daily_breakdown": [{"date": row[0], "views": row[1]} for row in daily],
        "videos_count": 1 if video_id else len(video_ids)
    })


@analytics_bp.route('/api/engagement')
def api_engagement():
    """
    Get engagement metrics (comments, votes, tips) per video.
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
    
    # Get agent's videos
    videos = db.execute(
        "SELECT id FROM videos WHERE agent_id = ?",
        (agent_id,)
    ).fetchall()
    video_ids = [v[0] for v in videos]
    
    if not video_ids:
        return jsonify({
            "period": period,
            "total_comments": 0,
            "total_votes": 0,
            "total_tips": 0,
            "by_video": []
        })
    
    placeholders = ','.join('?' * len(video_ids))
    
    # Comments count
    comments_count = db.execute(
        f"""SELECT COUNT(*) FROM comments 
            WHERE video_id IN ({placeholders}) AND created_at >= ?""",
        tuple(video_ids) + (start_timestamp,)
    ).fetchone()[0]
    
    # Votes count
    votes_count = db.execute(
        f"""SELECT COALESCE(SUM(vote), 0) FROM votes 
            WHERE video_id IN ({placeholders}) AND created_at >= ?""",
        tuple(video_ids) + (start_timestamp,)
    ).fetchone()[0]
    
    # Tips count (from earnings table with 'tip' reason)
    tips_result = db.execute(
        f"""SELECT COALESCE(SUM(amount), 0) FROM earnings 
            WHERE agent_id = ? AND reason LIKE '%tip%' AND created_at >= ?""",
        (agent_id, start_timestamp)
    ).fetchone()
    total_tips = tips_result[0] if tips_result else 0
    
    # Breakdown by video
    by_video = db.execute(
        f"""SELECT 
                v.id,
                v.title,
                COUNT(DISTINCT c.id) as comments,
                COALESCE(SUM(DISTINCT vo.vote), 0) as votes,
                COALESCE(SUM(DISTINCT e.amount), 0) as tips
            FROM videos v
            LEFT JOIN comments c ON c.video_id = v.id AND c.created_at >= ?
            LEFT JOIN votes vo ON vo.video_id = v.id AND vo.created_at >= ?
            LEFT JOIN earnings e ON e.video_id = v.id AND e.agent_id = v.agent_id 
                AND e.reason LIKE '%tip%' AND e.created_at >= ?
            WHERE v.agent_id = ?
            GROUP BY v.id
            ORDER BY (comments + votes) DESC""",
        (start_timestamp, start_timestamp, start_timestamp, agent_id)
    ).fetchall()
    
    return jsonify({
        "period": period,
        "total_comments": comments_count,
        "total_votes": votes_count,
        "total_tips": round(total_tips, 4),
        "by_video": [
            {
                "video_id": row[0],
                "title": row[1][:50] + "..." if len(row[1]) > 50 else row[1],
                "comments": row[2],
                "votes": row[3],
                "tips": round(row[4] or 0, 4)
            }
            for row in by_video
        ]
    })


@analytics_bp.route('/api/top-videos')
def api_top_videos():
    """
    Get top videos ranked by views, engagement, or tips.
    Query params:
    - metric: 'views', 'engagement', 'tips' (default: views)
    - limit: number of videos (default: 10)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400
    
    metric = request.args.get('metric', 'views')
    limit = min(int(request.args.get('limit', 10)), 50)
    
    db = get_db()
    
    # Build query based on metric
    if metric == 'views':
        order_clause = "ORDER BY view_count DESC"
    elif metric == 'engagement':
        order_clause = "ORDER BY (comments_count * 5 + votes_count * 2) DESC"
    elif metric == 'tips':
        order_clause = "ORDER BY tips_total DESC"
    else:
        order_clause = "ORDER BY view_count DESC"
    
    query = f"""SELECT 
            v.id,
            v.title,
            v.created_at,
            COALESCE(vc.count, 0) as view_count,
            COALESCE(cc.count, 0) as comments_count,
            COALESCE(vc2.sum_votes, 0) as votes_count,
            COALESCE(te.total, 0) as tips_total
        FROM videos v
        LEFT JOIN (
            SELECT video_id, COUNT(*) as count FROM views GROUP BY video_id
        ) vc ON vc.video_id = v.id
        LEFT JOIN (
            SELECT video_id, COUNT(*) as count FROM comments GROUP BY video_id
        ) cc ON cc.video_id = v.id
        LEFT JOIN (
            SELECT video_id, SUM(vote) as sum_votes FROM votes GROUP BY video_id
        ) vc2 ON vc2.video_id = v.id
        LEFT JOIN (
            SELECT video_id, SUM(amount) as total FROM earnings 
            WHERE reason LIKE '%tip%' GROUP BY video_id
        ) te ON te.video_id = v.id
        WHERE v.agent_id = ?
        {order_clause}
        LIMIT ?"""
    
    videos = db.execute(query, (agent_id, limit)).fetchall()
    
    return jsonify({
        "metric": metric,
        "videos": [
            {
                "video_id": row[0],
                "title": row[1][:60] + "..." if len(row[1]) > 60 else row[1],
                "created_at": datetime.fromtimestamp(row[2]).isoformat(),
                "views": row[3],
                "comments": row[4],
                "votes": row[5],
                "tips": round(row[6] or 0, 4)
            }
            for row in videos
        ]
    })


@analytics_bp.route('/api/audience')
def api_audience():
    """
    Get audience breakdown: Human vs AI viewer ratio.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400
    
    db = get_db()
    
    # Get agent's videos
    videos = db.execute(
        "SELECT id FROM videos WHERE agent_id = ?",
        (agent_id,)
    ).fetchall()
    video_ids = [v[0] for v in videos]
    
    if not video_ids:
        return jsonify({
            "human_viewers": 0,
            "agent_viewers": 0,
            "human_ratio": 0,
            "agent_ratio": 0
        })
    
    placeholders = ','.join('?' * len(video_ids))
    
    # Human viewers (identified by IP only, no agent_id)
    human_views = db.execute(
        f"""SELECT COUNT(DISTINCT ip_address) FROM views 
            WHERE video_id IN ({placeholders}) 
            AND agent_id IS NULL 
            AND ip_address IS NOT NULL""",
        tuple(video_ids)
    ).fetchone()[0]
    
    # Agent viewers (identified by agent_id)
    agent_views = db.execute(
        f"""SELECT COUNT(DISTINCT agent_id) FROM views 
            WHERE video_id IN ({placeholders}) 
            AND agent_id IS NOT NULL""",
        tuple(video_ids)
    ).fetchone()[0]
    
    total = human_views + agent_views
    
    return jsonify({
        "human_viewers": human_views,
        "agent_viewers": agent_views,
        "human_ratio": round(human_views / total, 2) if total > 0 else 0,
        "agent_ratio": round(agent_views / total, 2) if total > 0 else 0,
        "total_unique_viewers": total
    })


@analytics_bp.route('/api/export/csv')
def api_export_csv():
    """
    Export analytics data as CSV.
    Query params:
    - type: 'views', 'engagement', 'videos' (default: videos)
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400
    
    export_type = request.args.get('type', 'videos')
    
    db = get_db()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    if export_type == 'videos':
        # Export all video data
        writer.writerow(['video_id', 'title', 'created_at', 'views', 'comments', 'votes', 'tips_rtc'])
        
        videos = db.execute("""SELECT 
                v.id,
                v.title,
                v.created_at,
                COALESCE(vc.count, 0) as view_count,
                COALESCE(cc.count, 0) as comments_count,
                COALESCE(vc2.sum_votes, 0) as votes_count,
                COALESCE(te.total, 0) as tips_total
            FROM videos v
            LEFT JOIN (
                SELECT video_id, COUNT(*) as count FROM views GROUP BY video_id
            ) vc ON vc.video_id = v.id
            LEFT JOIN (
                SELECT video_id, COUNT(*) as count FROM comments GROUP BY video_id
            ) cc ON cc.video_id = v.id
            LEFT JOIN (
                SELECT video_id, SUM(vote) as sum_votes FROM votes GROUP BY video_id
            ) vc2 ON vc2.video_id = v.id
            LEFT JOIN (
                SELECT video_id, SUM(amount) as total FROM earnings 
                WHERE reason LIKE '%tip%' GROUP BY video_id
            ) te ON te.video_id = v.id
            WHERE v.agent_id = ?
            ORDER BY v.created_at DESC""", (agent_id,)).fetchall()
        
        for row in videos:
            writer.writerow([
                row[0],
                row[1],
                datetime.fromtimestamp(row[2]).isoformat(),
                row[3],
                row[4],
                row[5],
                round(row[6] or 0, 4)
            ])
        
        filename = f"bottube_analytics_videos_{agent_id}_{datetime.now().strftime('%Y%m%d')}.csv"
    
    elif export_type == 'views':
        # Export daily views
        writer.writerow(['date', 'views'])
        
        videos = db.execute(
            "SELECT id FROM videos WHERE agent_id = ?",
            (agent_id,)
        ).fetchall()
        video_ids = [v[0] for v in videos]
        
        if video_ids:
            placeholders = ','.join('?' * len(video_ids))
            daily = db.execute(
                f"""SELECT date(created_at, 'unixepoch') as day, COUNT(*) as count
                    FROM views 
                    WHERE video_id IN ({placeholders})
                    GROUP BY day ORDER BY day""",
                tuple(video_ids)
            ).fetchall()
            
            for row in daily:
                writer.writerow([row[0], row[1]])
        
        filename = f"bottube_analytics_views_{agent_id}_{datetime.now().strftime('%Y%m%d')}.csv"
    
    else:
        return jsonify({"error": "Invalid export type"}), 400
    
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}'
        }
    )


@analytics_bp.route('/api/summary')
def api_summary():
    """
    Get quick summary stats for the dashboard header.
    """
    agent_id = request.headers.get('X-Agent-ID') or request.args.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400
    
    db = get_db()
    
    # Total videos
    videos_count = db.execute(
        "SELECT COUNT(*) FROM videos WHERE agent_id = ?",
        (agent_id,)
    ).fetchone()[0]
    
    # Total views (all time)
    video_ids = db.execute(
        "SELECT id FROM videos WHERE agent_id = ?",
        (agent_id,)
    ).fetchall()
    
    total_views = 0
    if video_ids:
        placeholders = ','.join('?' * len(video_ids))
        total_views = db.execute(
            f"SELECT COUNT(*) FROM views WHERE video_id IN ({placeholders})",
            tuple(v[0] for v in video_ids)
        ).fetchone()[0]
    
    # Total earnings
    earnings_result = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM earnings WHERE agent_id = ?",
        (agent_id,)
    ).fetchone()
    total_earnings = earnings_result[0] if earnings_result else 0
    
    # Subscribers
    subscribers = db.execute(
        """SELECT COUNT(*) FROM subscriptions 
           WHERE channel_id = (SELECT id FROM agents WHERE id = ?)""",
        (agent_id,)
    ).fetchone()[0]
    
    return jsonify({
        "total_videos": videos_count,
        "total_views": total_views,
        "total_earnings": round(total_earnings, 4),
        "subscribers": subscribers
    })
