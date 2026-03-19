import sqlite3
from flask import Blueprint, request, jsonify, g, session
from bottube_server import get_db
import uuid
import time

tv_api = Blueprint('tv_api', __name__, url_prefix='/api/tv')


@tv_api.route('/auth/device_code', methods=['POST'])
def create_device_code():
    """Generate a device code for TV authentication."""
    device_code = str(uuid.uuid4())
    user_code = f"{device_code[:4].upper()}-{device_code[4:8].upper()}"
    verification_uri = request.host_url + 'tv/activate'
    expires_in = 600  # 10 minutes
    
    db = get_db()
    db.execute(
        'INSERT INTO tv_device_codes (device_code, user_code, expires_at, verified) VALUES (?, ?, ?, ?)',
        (device_code, user_code, int(time.time()) + expires_in, 0)
    )
    db.commit()
    
    return jsonify({
        'device_code': device_code,
        'user_code': user_code,
        'verification_uri': verification_uri,
        'verification_uri_complete': f"{verification_uri}?user_code={user_code}",
        'expires_in': expires_in,
        'interval': 5
    })


@tv_api.route('/auth/token', methods=['POST'])
def get_device_token():
    """Poll for device token after user verification."""
    data = request.get_json()
    device_code = data.get('device_code')
    
    if not device_code:
        return jsonify({'error': 'device_code required'}), 400
    
    db = get_db()
    result = db.execute(
        'SELECT * FROM tv_device_codes WHERE device_code = ? AND expires_at > ?',
        (device_code, int(time.time()))
    ).fetchone()
    
    if not result:
        return jsonify({'error': 'expired_token'}), 400
    
    if not result['verified']:
        return jsonify({'error': 'authorization_pending'}), 400
    
    # Generate access token
    access_token = str(uuid.uuid4())
    user_id = result['user_id']
    
    db.execute(
        'INSERT INTO tv_access_tokens (access_token, user_id, device_code, expires_at) VALUES (?, ?, ?, ?)',
        (access_token, user_id, device_code, int(time.time()) + 86400)  # 24 hour token
    )
    db.commit()
    
    return jsonify({
        'access_token': access_token,
        'token_type': 'Bearer',
        'expires_in': 86400
    })


@tv_api.route('/videos/trending', methods=['GET'])
def get_trending_videos():
    """Get trending videos for TV interface."""
    db = get_db()
    videos = db.execute(
        '''SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration, 
                  u.username, v.view_count, v.created_at
           FROM videos v
           JOIN users u ON v.user_id = u.id
           WHERE v.is_public = 1
           ORDER BY v.view_count DESC, v.created_at DESC
           LIMIT 50'''
    ).fetchall()
    
    video_list = []
    for video in videos:
        video_list.append({
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'thumbnail_url': video['thumbnail_url'],
            'duration': video['duration'],
            'username': video['username'],
            'view_count': video['view_count'],
            'created_at': video['created_at']
        })
    
    return jsonify({'videos': video_list})


@tv_api.route('/videos/recent', methods=['GET'])
def get_recent_videos():
    """Get recent videos for TV interface."""
    db = get_db()
    videos = db.execute(
        '''SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
                  u.username, v.view_count, v.created_at
           FROM videos v
           JOIN users u ON v.user_id = u.id
           WHERE v.is_public = 1
           ORDER BY v.created_at DESC
           LIMIT 50'''
    ).fetchall()
    
    video_list = []
    for video in videos:
        video_list.append({
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'thumbnail_url': video['thumbnail_url'],
            'duration': video['duration'],
            'username': video['username'],
            'view_count': video['view_count'],
            'created_at': video['created_at']
        })
    
    return jsonify({'videos': video_list})


@tv_api.route('/video/<int:video_id>', methods=['GET'])
def get_video_details(video_id):
    """Get video details and streaming URL for TV playback."""
    db = get_db()
    video = db.execute(
        '''SELECT v.id, v.title, v.description, v.filename, v.thumbnail_url,
                  v.duration, u.username, v.view_count, v.created_at
           FROM videos v
           JOIN users u ON v.user_id = u.id
           WHERE v.id = ? AND v.is_public = 1''',
        (video_id,)
    ).fetchone()
    
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    # Increment view count
    db.execute(
        'UPDATE videos SET view_count = view_count + 1 WHERE id = ?',
        (video_id,)
    )
    db.commit()
    
    return jsonify({
        'id': video['id'],
        'title': video['title'],
        'description': video['description'],
        'stream_url': f"{request.host_url}video/{video['filename']}",
        'thumbnail_url': video['thumbnail_url'],
        'duration': video['duration'],
        'username': video['username'],
        'view_count': video['view_count'] + 1,
        'created_at': video['created_at']
    })