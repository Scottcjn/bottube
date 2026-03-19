from flask import Blueprint, request, jsonify, g
from functools import wraps
from db import get_db
import sqlite3

tv_api = Blueprint('tv_api', __name__)

def tv_json_response(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if isinstance(result, dict):
            return jsonify(result)
        return result
    return wrapper

def get_video_data(video_id):
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
    
    return {
        'status': 'success',
        'videos': video_list,
        'total': len(video_list),
        'offset': offset,
        'limit': limit
    }

@tv_api.route('/api/tv/videos/recent')
@tv_json_response
def recent_videos():
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
    
    return {
        'status': 'success',
        'videos': video_list,
        'total': len(video_list),
        'offset': offset,
        'limit': limit
    }

@tv_api.route('/api/tv/videos/<int:video_id>')
@tv_json_response
def video_details(video_id):
    video = get_video_data(video_id)
    if not video:
        return {'status': 'error', 'message': 'Video not found'}, 404
    
    formatted = format_video_for_tv(video)
    if not formatted:
        return {'status': 'error', 'message': 'Video unavailable'}, 404
    
    return {
        'status': 'success',
        'video': formatted
    }

@tv_api.route('/api/tv/categories')
@tv_json_response
def categories():
    return {
        'status': 'success',
        'categories': [
            {
                'id': 'trending',
                'name': 'Trending',
                'endpoint': '/api/tv/videos/trending'
            },
            {
                'id': 'recent',
                'name': 'Recent',
                'endpoint': '/api/tv/videos/recent'
            }
        ]
    }

@tv_api.route('/api/tv/search')
@tv_json_response
def search_videos():
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    if not query:
        return {'status': 'error', 'message': 'Query parameter required'}, 400
    
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
    
    return {
        'status': 'success',
        'query': query,
        'videos': video_list,
        'total': len(video_list),
        'offset': offset,
        'limit': limit
    }

@tv_api.route('/api/tv/stream/<int:video_id>')
def stream_video(video_id):
    video = get_video_data(video_id)
    if not video:
        return jsonify({'status': 'error', 'message': 'Video not found'}), 404
    
    file_path = video[5]
    if not file_path:
        return jsonify({'status': 'error', 'message': 'Video file not available'}), 404
    
    # For TV clients, return the direct stream URL
    return jsonify({
        'status': 'success',
        'stream_url': f'/uploads/{file_path}',
        'content_type': 'video/mp4'
    })

@tv_api.route('/api/tv/thumbnail/<int:video_id>')
def video_thumbnail(video_id):
    # Return a placeholder thumbnail URL for now
    return jsonify({
        'status': 'success',
        'thumbnail_url': f'/static/thumbnails/default.jpg'
    })