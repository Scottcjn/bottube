import sqlite3
import json
from datetime import datetime, timedelta
from flask import g, jsonify, request
from bottube_server import get_db

def init_interaction_tables():
    """Initialize agent interaction tracking tables"""
    db = get_db()

    # Agent interactions table
    db.execute('''
        CREATE TABLE IF NOT EXISTS agent_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            interaction_type TEXT NOT NULL, -- 'view', 'comment', 'like', 'share'
            content_id TEXT, -- video_id or comment_id if applicable
            metadata TEXT, -- JSON for additional data
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT
        )
    ''')

    # Agent engagement metrics table
    db.execute('''
        CREATE TABLE IF NOT EXISTS agent_engagement_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL UNIQUE,
            total_views INTEGER DEFAULT 0,
            total_comments INTEGER DEFAULT 0,
            total_likes INTEGER DEFAULT 0,
            total_shares INTEGER DEFAULT 0,
            unique_viewers INTEGER DEFAULT 0,
            avg_watch_time REAL DEFAULT 0,
            engagement_rate REAL DEFAULT 0,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create indexes for better performance
    db.execute('CREATE INDEX IF NOT EXISTS idx_agent_interactions_agent_id ON agent_interactions(agent_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_agent_interactions_type ON agent_interactions(interaction_type)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_agent_interactions_timestamp ON agent_interactions(timestamp)')

    db.commit()

def track_interaction(agent_id, interaction_type, user_id=None, content_id=None, metadata=None):
    """Track an agent interaction"""
    db = get_db()

    # Use session user_id if not provided
    if not user_id and hasattr(g, 'user') and g.user:
        user_id = g.user['id']
    elif not user_id:
        user_id = 'anonymous'

    # Get request info
    ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR'))
    user_agent = request.headers.get('User-Agent')

    # Insert interaction record
    db.execute('''
        INSERT INTO agent_interactions
        (agent_id, user_id, interaction_type, content_id, metadata, ip_address, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (agent_id, user_id, interaction_type, content_id,
          json.dumps(metadata) if metadata else None, ip_address, user_agent))

    # Update engagement metrics
    update_engagement_metrics(agent_id, interaction_type)

    db.commit()

def update_engagement_metrics(agent_id, interaction_type):
    """Update engagement metrics for an agent"""
    db = get_db()

    # Get or create metrics record
    metrics = db.execute('''
        SELECT * FROM agent_engagement_metrics WHERE agent_id = ?
    ''', (agent_id,)).fetchone()

    if not metrics:
        db.execute('''
            INSERT INTO agent_engagement_metrics (agent_id) VALUES (?)
        ''', (agent_id,))
        metrics = {'total_views': 0, 'total_comments': 0, 'total_likes': 0, 'total_shares': 0}

    # Increment appropriate counter
    field_map = {
        'view': 'total_views',
        'comment': 'total_comments',
        'like': 'total_likes',
        'share': 'total_shares'
    }

    if interaction_type in field_map:
        field = field_map[interaction_type]
        db.execute(f'''
            UPDATE agent_engagement_metrics
            SET {field} = {field} + 1, last_updated = CURRENT_TIMESTAMP
            WHERE agent_id = ?
        ''', (agent_id,))

    # Update unique viewers count
    if interaction_type == 'view':
        unique_count = db.execute('''
            SELECT COUNT(DISTINCT user_id) FROM agent_interactions
            WHERE agent_id = ? AND interaction_type = 'view'
        ''', (agent_id,)).fetchone()[0]

        db.execute('''
            UPDATE agent_engagement_metrics
            SET unique_viewers = ? WHERE agent_id = ?
        ''', (unique_count, agent_id))

    # Calculate engagement rate
    calculate_engagement_rate(agent_id)

def calculate_engagement_rate(agent_id):
    """Calculate engagement rate for an agent"""
    db = get_db()

    metrics = db.execute('''
        SELECT total_views, total_comments, total_likes, total_shares
        FROM agent_engagement_metrics WHERE agent_id = ?
    ''', (agent_id,)).fetchone()

    if metrics and metrics[0] > 0:  # total_views > 0
        total_engagements = metrics[1] + metrics[2] + metrics[3]  # comments + likes + shares
        engagement_rate = (total_engagements / metrics[0]) * 100

        db.execute('''
            UPDATE agent_engagement_metrics
            SET engagement_rate = ? WHERE agent_id = ?
        ''', (engagement_rate, agent_id))

def get_agent_interactions(agent_id, limit=50, interaction_type=None, days_back=30):
    """Get recent interactions for an agent"""
    db = get_db()

    where_clause = 'WHERE agent_id = ?'
    params = [agent_id]

    if interaction_type:
        where_clause += ' AND interaction_type = ?'
        params.append(interaction_type)

    if days_back:
        cutoff_date = datetime.now() - timedelta(days=days_back)
        where_clause += ' AND timestamp >= ?'
        params.append(cutoff_date.isoformat())

    params.append(limit)

    interactions = db.execute(f'''
        SELECT * FROM agent_interactions
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ?
    ''', params).fetchall()

    return [dict(row) for row in interactions]

def get_agent_metrics(agent_id):
    """Get engagement metrics for an agent"""
    db = get_db()

    metrics = db.execute('''
        SELECT * FROM agent_engagement_metrics WHERE agent_id = ?
    ''', (agent_id,)).fetchone()

    if not metrics:
        return {
            'agent_id': agent_id,
            'total_views': 0,
            'total_comments': 0,
            'total_likes': 0,
            'total_shares': 0,
            'unique_viewers': 0,
            'avg_watch_time': 0,
            'engagement_rate': 0,
            'last_updated': None
        }

    return dict(metrics)

def get_interaction_trends(agent_id, days=7):
    """Get interaction trends over time"""
    db = get_db()

    cutoff_date = datetime.now() - timedelta(days=days)

    trends = db.execute('''
        SELECT
            DATE(timestamp) as date,
            interaction_type,
            COUNT(*) as count
        FROM agent_interactions
        WHERE agent_id = ? AND timestamp >= ?
        GROUP BY DATE(timestamp), interaction_type
        ORDER BY date DESC
    ''', (agent_id, cutoff_date.isoformat())).fetchall()

    # Format data for charting
    trend_data = {}
    for row in trends:
        date = row[0]
        interaction_type = row[1]
        count = row[2]

        if date not in trend_data:
            trend_data[date] = {}
        trend_data[date][interaction_type] = count

    return trend_data

def get_top_engaging_agents(limit=10, days_back=30):
    """Get agents with highest engagement"""
    db = get_db()

    cutoff_date = datetime.now() - timedelta(days=days_back)

    top_agents = db.execute('''
        SELECT
            agent_id,
            COUNT(*) as total_interactions,
            COUNT(DISTINCT user_id) as unique_users,
            SUM(CASE WHEN interaction_type = 'view' THEN 1 ELSE 0 END) as views,
            SUM(CASE WHEN interaction_type = 'like' THEN 1 ELSE 0 END) as likes,
            SUM(CASE WHEN interaction_type = 'comment' THEN 1 ELSE 0 END) as comments
        FROM agent_interactions
        WHERE timestamp >= ?
        GROUP BY agent_id
        ORDER BY total_interactions DESC
        LIMIT ?
    ''', (cutoff_date.isoformat(), limit)).fetchall()

    return [dict(row) for row in top_agents]

def get_user_interaction_history(user_id, limit=100):
    """Get interaction history for a specific user"""
    db = get_db()

    history = db.execute('''
        SELECT * FROM agent_interactions
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (user_id, limit)).fetchall()

    return [dict(row) for row in history]

def cleanup_old_interactions(days_to_keep=90):
    """Clean up old interaction data to manage database size"""
    db = get_db()

    cutoff_date = datetime.now() - timedelta(days=days_to_keep)

    deleted_count = db.execute('''
        DELETE FROM agent_interactions
        WHERE timestamp < ?
    ''', (cutoff_date.isoformat(),)).rowcount

    db.commit()
    return deleted_count

# Initialize tables when module is imported
init_interaction_tables()
