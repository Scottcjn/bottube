import sqlite3
import json
from functools import wraps
from flask import g
from bottube_server import get_db

def init_syndication_config():
    """Initialize syndication configuration tables"""
    db = get_db()

    # Platform configurations table
    db.execute('''
        CREATE TABLE IF NOT EXISTS platform_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform_name TEXT UNIQUE NOT NULL,
            enabled BOOLEAN DEFAULT 0,
            api_endpoint TEXT,
            credentials_encrypted TEXT,
            rate_limits TEXT,
            format_settings TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Bot/Agent specific settings
    db.execute('''
        CREATE TABLE IF NOT EXISTS agent_syndication_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            platform_name TEXT NOT NULL,
            enabled BOOLEAN DEFAULT 1,
            custom_settings TEXT,
            opt_in_status BOOLEAN DEFAULT 0,
            last_sync_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents (id),
            UNIQUE(agent_id, platform_name)
        )
    ''')

    # Scheduling preferences
    db.execute('''
        CREATE TABLE IF NOT EXISTS syndication_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            platform_name TEXT NOT NULL,
            schedule_type TEXT DEFAULT 'immediate',
            delay_minutes INTEGER DEFAULT 0,
            time_zones TEXT,
            recurring_pattern TEXT,
            active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents (id)
        )
    ''')

    # Engagement tracking
    db.execute('''
        CREATE TABLE IF NOT EXISTS syndication_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            platform_name TEXT NOT NULL,
            external_post_id TEXT,
            views_count INTEGER DEFAULT 0,
            likes_count INTEGER DEFAULT 0,
            shares_count INTEGER DEFAULT 0,
            comments_count INTEGER DEFAULT 0,
            click_throughs INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos (id),
            UNIQUE(video_id, platform_name)
        )
    ''')

    db.commit()

def get_platform_config(platform_name):
    """Get configuration for a specific platform"""
    db = get_db()
    config = db.execute(
        'SELECT * FROM platform_configs WHERE platform_name = ?',
        (platform_name,)
    ).fetchone()

    if config:
        return dict(config)
    return None

def update_platform_config(platform_name, **kwargs):
    """Update or create platform configuration"""
    db = get_db()

    config_data = {
        'enabled': kwargs.get('enabled', False),
        'api_endpoint': kwargs.get('api_endpoint'),
        'credentials_encrypted': kwargs.get('credentials_encrypted'),
        'rate_limits': json.dumps(kwargs.get('rate_limits', {})),
        'format_settings': json.dumps(kwargs.get('format_settings', {}))
    }

    existing = get_platform_config(platform_name)

    if existing:
        db.execute('''
            UPDATE platform_configs
            SET enabled = ?, api_endpoint = ?, credentials_encrypted = ?,
                rate_limits = ?, format_settings = ?, updated_at = CURRENT_TIMESTAMP
            WHERE platform_name = ?
        ''', (
            config_data['enabled'], config_data['api_endpoint'],
            config_data['credentials_encrypted'], config_data['rate_limits'],
            config_data['format_settings'], platform_name
        ))
    else:
        db.execute('''
            INSERT INTO platform_configs
            (platform_name, enabled, api_endpoint, credentials_encrypted, rate_limits, format_settings)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            platform_name, config_data['enabled'], config_data['api_endpoint'],
            config_data['credentials_encrypted'], config_data['rate_limits'],
            config_data['format_settings']
        ))

    db.commit()

def get_agent_syndication_settings(agent_id, platform_name=None):
    """Get syndication settings for an agent"""
    db = get_db()

    if platform_name:
        settings = db.execute('''
            SELECT * FROM agent_syndication_settings
            WHERE agent_id = ? AND platform_name = ?
        ''', (agent_id, platform_name)).fetchone()
        return dict(settings) if settings else None
    else:
        settings = db.execute('''
            SELECT * FROM agent_syndication_settings
            WHERE agent_id = ?
        ''', (agent_id,)).fetchall()
        return [dict(row) for row in settings]

def set_agent_platform_opt_in(agent_id, platform_name, opt_in=True, custom_settings=None):
    """Set opt-in status for agent on specific platform"""
    db = get_db()

    existing = get_agent_syndication_settings(agent_id, platform_name)

    settings_json = json.dumps(custom_settings) if custom_settings else None

    if existing:
        db.execute('''
            UPDATE agent_syndication_settings
            SET opt_in_status = ?, custom_settings = ?, enabled = ?
            WHERE agent_id = ? AND platform_name = ?
        ''', (opt_in, settings_json, opt_in, agent_id, platform_name))
    else:
        db.execute('''
            INSERT INTO agent_syndication_settings
            (agent_id, platform_name, opt_in_status, enabled, custom_settings)
            VALUES (?, ?, ?, ?, ?)
        ''', (agent_id, platform_name, opt_in, opt_in, settings_json))

    db.commit()

def get_enabled_platforms_for_agent(agent_id):
    """Get list of enabled platforms for an agent"""
    db = get_db()

    platforms = db.execute('''
        SELECT ass.platform_name, pc.api_endpoint, pc.format_settings, ass.custom_settings
        FROM agent_syndication_settings ass
        JOIN platform_configs pc ON ass.platform_name = pc.platform_name
        WHERE ass.agent_id = ? AND ass.enabled = 1 AND ass.opt_in_status = 1 AND pc.enabled = 1
    ''', (agent_id,)).fetchall()

    return [dict(row) for row in platforms]

def update_syndication_schedule(agent_id, platform_name, schedule_type='immediate', delay_minutes=0, recurring_pattern=None):
    """Update scheduling preferences for agent/platform combination"""
    db = get_db()

    existing = db.execute('''
        SELECT id FROM syndication_schedules
        WHERE agent_id = ? AND platform_name = ?
    ''', (agent_id, platform_name)).fetchone()

    if existing:
        db.execute('''
            UPDATE syndication_schedules
            SET schedule_type = ?, delay_minutes = ?, recurring_pattern = ?
            WHERE agent_id = ? AND platform_name = ?
        ''', (schedule_type, delay_minutes, recurring_pattern, agent_id, platform_name))
    else:
        db.execute('''
            INSERT INTO syndication_schedules
            (agent_id, platform_name, schedule_type, delay_minutes, recurring_pattern)
            VALUES (?, ?, ?, ?, ?)
        ''', (agent_id, platform_name, schedule_type, delay_minutes, recurring_pattern))

    db.commit()

def track_syndication_metrics(video_id, platform_name, external_post_id, metrics=None):
    """Track engagement metrics for syndicated content"""
    db = get_db()

    if metrics is None:
        metrics = {}

    existing = db.execute('''
        SELECT id FROM syndication_metrics
        WHERE video_id = ? AND platform_name = ?
    ''', (video_id, platform_name)).fetchone()

    if existing:
        db.execute('''
            UPDATE syndication_metrics
            SET external_post_id = ?, views_count = ?, likes_count = ?,
                shares_count = ?, comments_count = ?, click_throughs = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE video_id = ? AND platform_name = ?
        ''', (
            external_post_id, metrics.get('views', 0), metrics.get('likes', 0),
            metrics.get('shares', 0), metrics.get('comments', 0),
            metrics.get('click_throughs', 0), video_id, platform_name
        ))
    else:
        db.execute('''
            INSERT INTO syndication_metrics
            (video_id, platform_name, external_post_id, views_count, likes_count,
             shares_count, comments_count, click_throughs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            video_id, platform_name, external_post_id, metrics.get('views', 0),
            metrics.get('likes', 0), metrics.get('shares', 0),
            metrics.get('comments', 0), metrics.get('click_throughs', 0)
        ))

    db.commit()

def get_syndication_metrics(video_id, platform_name=None):
    """Get engagement metrics for syndicated content"""
    db = get_db()

    if platform_name:
        metrics = db.execute('''
            SELECT * FROM syndication_metrics
            WHERE video_id = ? AND platform_name = ?
        ''', (video_id, platform_name)).fetchone()
        return dict(metrics) if metrics else None
    else:
        metrics = db.execute('''
            SELECT * FROM syndication_metrics WHERE video_id = ?
        ''', (video_id,)).fetchall()
        return [dict(row) for row in metrics]

def get_all_platform_configs():
    """Get all platform configurations"""
    db = get_db()
    configs = db.execute('SELECT * FROM platform_configs ORDER BY platform_name').fetchall()
    return [dict(row) for row in configs]

SUPPORTED_PLATFORMS = [
    'youtube_shorts',
    'tiktok',
    'instagram_reels',
    'twitter_video',
    'linkedin_video',
    'facebook_video',
    'pinterest_video',
    'snapchat_spotlight'
]

def validate_platform_name(platform_name):
    """Validate that platform name is supported"""
    return platform_name in SUPPORTED_PLATFORMS

def require_syndication_config(f):
    """Decorator to ensure syndication config is initialized"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_syndication_config()
        return f(*args, **kwargs)
    return decorated_function
