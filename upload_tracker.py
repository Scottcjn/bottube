import sqlite3
import datetime
from typing import Dict, List, Optional, Any
from flask import g


def get_db():
    """Get database connection from Flask context."""
    if 'db' not in g:
        g.db = sqlite3.connect('bottube.db')
        g.db.row_factory = sqlite3.Row
    return g.db


def init_upload_tracking_db():
    """Initialize upload tracking tables."""
    db = get_db()

    # Daily upload tracking
    db.execute('''
        CREATE TABLE IF NOT EXISTS daily_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_date DATE NOT NULL UNIQUE,
            upload_count INTEGER DEFAULT 0,
            target_count INTEGER DEFAULT 1,
            completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Video upload records
    db.execute('''
        CREATE TABLE IF NOT EXISTS upload_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            file_path TEXT,
            file_size INTEGER,
            duration_seconds INTEGER,
            upload_date DATE NOT NULL,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            metadata TEXT
        )
    ''')

    # Upload queue for scheduled uploads
    db.execute('''
        CREATE TABLE IF NOT EXISTS upload_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            file_path TEXT NOT NULL,
            scheduled_date DATE NOT NULL,
            priority INTEGER DEFAULT 1,
            status TEXT DEFAULT 'queued',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
    ''')

    db.commit()


def get_daily_status(target_date: str = None) -> Dict[str, Any]:
    """Get upload status for a specific date."""
    if target_date is None:
        target_date = datetime.date.today().isoformat()

    db = get_db()

    # Get or create daily record
    daily_record = db.execute(
        'SELECT * FROM daily_uploads WHERE upload_date = ?',
        (target_date,)
    ).fetchone()

    if not daily_record:
        db.execute(
            'INSERT INTO daily_uploads (upload_date) VALUES (?)',
            (target_date,)
        )
        db.commit()
        daily_record = db.execute(
            'SELECT * FROM daily_uploads WHERE upload_date = ?',
            (target_date,)
        ).fetchone()

    # Get upload records for the date
    uploads = db.execute(
        'SELECT * FROM upload_records WHERE upload_date = ? ORDER BY upload_time DESC',
        (target_date,)
    ).fetchall()

    return {
        'date': target_date,
        'target_count': daily_record['target_count'],
        'upload_count': daily_record['upload_count'],
        'completed': bool(daily_record['completed']),
        'uploads': [dict(upload) for upload in uploads],
        'remaining': max(0, daily_record['target_count'] - daily_record['upload_count'])
    }


def check_duplicate_upload(title: str, date: str = None) -> bool:
    """Check if a video with the same title was already uploaded today."""
    if date is None:
        date = datetime.date.today().isoformat()

    db = get_db()
    existing = db.execute(
        'SELECT id FROM upload_records WHERE title = ? AND upload_date = ? AND status != "failed"',
        (title, date)
    ).fetchone()

    return existing is not None


def record_upload(title: str, description: str = None, file_path: str = None,
                 video_id: str = None, file_size: int = None,
                 duration_seconds: int = None, metadata: str = None) -> int:
    """Record a successful upload."""
    upload_date = datetime.date.today().isoformat()

    # Check for duplicate
    if check_duplicate_upload(title, upload_date):
        raise ValueError(f"Video with title '{title}' already uploaded today")

    db = get_db()

    # Insert upload record
    cursor = db.execute('''
        INSERT INTO upload_records
        (video_id, title, description, file_path, file_size, duration_seconds,
         upload_date, status, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?)
    ''', (video_id, title, description, file_path, file_size, duration_seconds,
          upload_date, metadata))

    upload_id = cursor.lastrowid

    # Update daily counter
    db.execute('''
        UPDATE daily_uploads
        SET upload_count = upload_count + 1,
            completed = (upload_count + 1 >= target_count)
        WHERE upload_date = ?
    ''', (upload_date,))

    # Create daily record if it doesn't exist
    if db.execute('SELECT id FROM daily_uploads WHERE upload_date = ?', (upload_date,)).fetchone() is None:
        db.execute('INSERT INTO daily_uploads (upload_date, upload_count) VALUES (?, 1)', (upload_date,))

    db.commit()
    return upload_id


def record_upload_failure(title: str, error_message: str, file_path: str = None):
    """Record a failed upload attempt."""
    upload_date = datetime.date.today().isoformat()

    db = get_db()
    db.execute('''
        INSERT INTO upload_records
        (title, file_path, upload_date, status, error_message)
        VALUES (?, ?, ?, 'failed', ?)
    ''', (title, file_path, upload_date, error_message))
    db.commit()


def get_upload_history(days: int = 7) -> List[Dict[str, Any]]:
    """Get upload history for the last N days."""
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days-1)

    db = get_db()

    # Get daily summaries
    daily_stats = db.execute('''
        SELECT upload_date, upload_count, target_count, completed
        FROM daily_uploads
        WHERE upload_date >= ? AND upload_date <= ?
        ORDER BY upload_date DESC
    ''', (start_date.isoformat(), end_date.isoformat())).fetchall()

    # Get recent uploads
    recent_uploads = db.execute('''
        SELECT * FROM upload_records
        WHERE upload_date >= ? AND upload_date <= ?
        ORDER BY upload_time DESC
        LIMIT 50
    ''', (start_date.isoformat(), end_date.isoformat())).fetchall()

    return {
        'period': {'start': start_date.isoformat(), 'end': end_date.isoformat()},
        'daily_stats': [dict(stat) for stat in daily_stats],
        'recent_uploads': [dict(upload) for upload in recent_uploads],
        'total_uploads': len(recent_uploads),
        'success_rate': len([u for u in recent_uploads if u['status'] == 'completed']) / max(1, len(recent_uploads))
    }


def add_to_queue(title: str, description: str, file_path: str,
                scheduled_date: str = None, priority: int = 1) -> int:
    """Add video to upload queue."""
    if scheduled_date is None:
        scheduled_date = datetime.date.today().isoformat()

    db = get_db()
    cursor = db.execute('''
        INSERT INTO upload_queue (title, description, file_path, scheduled_date, priority)
        VALUES (?, ?, ?, ?, ?)
    ''', (title, description, file_path, scheduled_date, priority))

    db.commit()
    return cursor.lastrowid


def get_pending_uploads(date: str = None) -> List[Dict[str, Any]]:
    """Get pending uploads for a specific date."""
    if date is None:
        date = datetime.date.today().isoformat()

    db = get_db()
    pending = db.execute('''
        SELECT * FROM upload_queue
        WHERE scheduled_date = ? AND status = 'queued'
        ORDER BY priority DESC, created_at ASC
    ''', (date,)).fetchall()

    return [dict(item) for item in pending]


def mark_queue_item_processed(queue_id: int, status: str = 'processed'):
    """Mark a queue item as processed."""
    db = get_db()
    db.execute('''
        UPDATE upload_queue
        SET status = ?, processed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (status, queue_id))
    db.commit()


def get_streak_info() -> Dict[str, Any]:
    """Get current upload streak information."""
    db = get_db()

    # Get completed days in descending order
    completed_days = db.execute('''
        SELECT upload_date FROM daily_uploads
        WHERE completed = TRUE
        ORDER BY upload_date DESC
    ''').fetchall()

    if not completed_days:
        return {'current_streak': 0, 'longest_streak': 0, 'last_upload': None}

    # Calculate current streak
    current_streak = 0
    today = datetime.date.today()
    check_date = today

    completed_dates = [datetime.date.fromisoformat(row['upload_date']) for row in completed_days]

    # Count consecutive days from today backwards
    while check_date in completed_dates:
        current_streak += 1
        check_date -= datetime.timedelta(days=1)

    # Calculate longest streak
    longest_streak = 0
    temp_streak = 0
    prev_date = None

    for date in sorted(completed_dates):
        if prev_date is None or (date - prev_date).days == 1:
            temp_streak += 1
            longest_streak = max(longest_streak, temp_streak)
        else:
            temp_streak = 1
        prev_date = date

    return {
        'current_streak': current_streak,
        'longest_streak': longest_streak,
        'last_upload': completed_dates[0].isoformat() if completed_dates else None,
        'total_days_uploaded': len(completed_dates)
    }
