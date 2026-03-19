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
    video_list = []

    for video in videos:
        formatted = format_video_for_tv(video)
        if formatted:
            video_list.append(formatted)

    return {'videos': video_list, 'total': len(video_list)}


@tv_api.route('/api/tv/videos/recent')
@tv_json_response
def recent_videos():
    """Get recent videos for TV interface"""
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT v.id, v.title, v.description, v.view_count, v.created_at,
               v.file_path, v.duration, u.username, u.id as user_id
        FROM videos v
        JOIN users u ON v.user_id = u.id
        ORDER BY v.created_at DESC
        LIMIT ? OFFSET ?
    ''', (limit, offset))

    videos = cursor.fetchall()
    video_list = []

    for video in videos:
        formatted = format_video_for_tv(video)
        if formatted:
            video_list.append(formatted)

    return {'videos': video_list, 'total': len(video_list)}


@tv_api.route('/api/tv/videos/<int:video_id>')
@tv_json_response
def get_video(video_id):
    """Get specific video data for TV interface"""
    video_data = get_video_data(video_id)
    if not video_data:
        return {'error': 'Video not found'}, 404

    formatted = format_video_for_tv(video_data)
    return {'video': formatted}


@tv_api.route('/api/tv/categories')
@tv_json_response
def get_categories():
    """Get video categories for TV interface"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT DISTINCT category, COUNT(*) as video_count
        FROM videos
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY video_count DESC
    ''')

    categories = cursor.fetchall()
    category_list = []

    for cat in categories:
        category_list.append({
            'name': cat[0],
            'video_count': cat[1]
        })

    return {'categories': category_list}


@tv_api.route('/api/tv/search')
@tv_json_response
def search_videos():
    """Search videos for TV interface"""
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)

    if not query:
        return {'videos': [], 'total': 0}

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT v.id, v.title, v.description, v.view_count, v.created_at,
               v.file_path, v.duration, u.username, u.id as user_id
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.title LIKE ? OR v.description LIKE ?
        ORDER BY v.view_count DESC, v.created_at DESC
        LIMIT ? OFFSET ?
    ''', (f'%{query}%', f'%{query}%', limit, offset))

    videos = cursor.fetchall()
    video_list = []

    for video in videos:
        formatted = format_video_for_tv(video)
        if formatted:
            video_list.append(formatted)

    return {'videos': video_list, 'total': len(video_list), 'query': query}