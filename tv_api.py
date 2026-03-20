from flask import Blueprint, request, jsonify, g
from functools import wraps
from db import get_db
import sqlite3

tv_api = Blueprint('tv_api', __name__)


def tv_json_response(func):
    """Decorator for TV API responses"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if isinstance(result, dict):
            return jsonify(result)
        return result
    return wrapper


def get_video_data(video_id):
    """Get video data by ID"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT v.id, v.title, v.description, v.view_count, v.created_at,
               v.file_path, v.duration, u.username, u.id as user_id
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.id = ?
    ''', (video_id,))
    return cursor.fetchone()


def format_video_for_tv(video_row):
    """Format video data for TV interface"""
    if not video_row:
        return None

    return {
        'id': video_row[0],
        'title': video_row[1],
        'description': video_row[2] or '',
        'views': video_row[3] or 0,
        'created': video_row[4],
        'duration': video_row[6] or 0,
        'username': video_row[7],
        'user_id': video_row[8],
        'thumbnail_url': f'/api/tv/thumbnail/{video_row[0]}',
        'stream_url': f'/api/tv/stream/{video_row[0]}'
    }


@tv_api.route('/api/tv/videos/trending')
@tv_json_response
def trending_videos():
    """Get trending videos for TV interface"""
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT v.id, v.title, v.description, v.view_count, v.created_at,
               v.file_path, v.duration, u.username, u.id as user_id
        FROM videos v
        JOIN users u ON v.user_id = u.id
        ORDER BY v.view_count DESC, v.created_at DESC
        LIMIT ? OFFSET ?
    ''', (limit, offset))

    videos = cursor.fetchall()
    video_list = [format_video_for_tv(video) for video in videos]

    return {
        'videos': video_list,
        'total': len(video_list),
        'offset': offset
    }
