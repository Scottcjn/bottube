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
        (access_token, user_id, device_code, int(time.time()) + 86400)  # 24 hours
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
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'unauthorized'}), 401
    
    access_token = auth_header.split(' ')[1]
    
    db = get_db()
    token_result = db.execute(
        'SELECT user_id FROM tv_access_tokens WHERE access_token = ? AND expires_at > ?',
        (access_token, int(time.time()))
    ).fetchone()
    
    if not token_result:
        return jsonify({'error': 'invalid_token'}), 401
    
    # Get trending videos
    videos = db.execute(
        'SELECT id, title, description, filename, thumbnail_path, created_at, views FROM videos ORDER BY views DESC LIMIT 50'
    ).fetchall()
    
    video_list = []
    for video in videos:
        video_list.append({
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'thumbnail_url': f"/static/thumbnails/{video['thumbnail_path']}" if video['thumbnail_path'] else None,
            'video_url': f"/static/videos/{video['filename']}",
            'views': video['views'],
            'created_at': video['created_at']
        })
    
    return jsonify({'videos': video_list})


@tv_api.route('/videos/recent', methods=['GET'])
def get_recent_videos():
    """Get recent videos for TV interface."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'unauthorized'}), 401
    
    access_token = auth_header.split(' ')[1]
    
    db = get_db()
    token_result = db.execute(
        'SELECT user_id FROM tv_access_tokens WHERE access_token = ? AND expires_at > ?',
        (access_token, int(time.time()))
    ).fetchone()
    
    if not token_result:
        return jsonify({'error': 'invalid_token'}), 401
    
    # Get recent videos
    videos = db.execute(
        'SELECT id, title, description, filename, thumbnail_path, created_at, views FROM videos ORDER BY created_at DESC LIMIT 50'
    ).fetchall()
    
    video_list = []
    for video in videos:
        video_list.append({
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'thumbnail_url': f"/static/thumbnails/{video['thumbnail_path']}" if video['thumbnail_path'] else None,
            'video_url': f"/static/videos/{video['filename']}",
            'views': video['views'],
            'created_at': video['created_at']
        })
    
    return jsonify({'videos': video_list})