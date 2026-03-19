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
    db.execute('DELETE FROM tv_device_codes WHERE device_code = ?', (device_code,))
    db.commit()
    
    return jsonify({
        'access_token': access_token,
        'token_type': 'bearer',
        'expires_in': 86400
    })

def get_tv_user():
    """Get authenticated TV user from access token."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header[7:]
    db = get_db()
    result = db.execute(
        '''SELECT u.id, u.username 
           FROM tv_access_tokens t 
           JOIN users u ON t.user_id = u.id 
           WHERE t.access_token = ? AND t.expires_at > ?''',
        (token, int(time.time()))
    ).fetchone()
    
    return result

@tv_api.route('/videos/trending')
def trending_videos():
    """Get trending videos for TV interface."""
    limit = min(int(request.args.get('limit', 20)), 50)
    offset = int(request.args.get('offset', 0))
    
    db = get_db()
    videos = db.execute(
        '''SELECT v.id, v.title, v.description, v.thumbnail_url, v.video_url, 
                  v.duration, v.upload_date, u.username as uploader,
                  COUNT(l.id) as view_count
           FROM videos v
           JOIN users u ON v.user_id = u.id
           LEFT JOIN video_views l ON v.id = l.video_id
           WHERE v.is_processed = 1
           GROUP BY v.id
           ORDER BY view_count DESC, v.upload_date DESC
           LIMIT ? OFFSET ?''',
        (limit, offset)
    ).fetchall()
    
    return jsonify({
        'videos': [dict(video) for video in videos],
        'has_more': len(videos) == limit
    })

@tv_api.route('/videos/recent')
def recent_videos():
    """Get recently uploaded videos for TV interface."""
    limit = min(int(request.args.get('limit', 20)), 50)
    offset = int(request.args.get('offset', 0))
    
    db = get_db()
    videos = db.execute(
        '''SELECT v.id, v.title, v.description, v.thumbnail_url, v.video_url,
                  v.duration, v.upload_date, u.username as uploader
           FROM videos v
           JOIN users u ON v.user_id = u.id
           WHERE v.is_processed = 1
           ORDER BY v.upload_date DESC
           LIMIT ? OFFSET ?''',
        (limit, offset)
    ).fetchall()
    
    return jsonify({
        'videos': [dict(video) for video in videos],
        'has_more': len(videos) == limit
    })

@tv_api.route('/videos/<int:video_id>')
def get_video_details(video_id):
    """Get detailed video information for playback."""
    db = get_db()
    video = db.execute(
        '''SELECT v.id, v.title, v.description, v.thumbnail_url, v.video_url,
                  v.duration, v.upload_date, u.username as uploader, u.id as uploader_id
           FROM videos v
           JOIN users u ON v.user_id = u.id
           WHERE v.id = ? AND v.is_processed = 1''',
        (video_id,)
    ).fetchone()
    
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    # Record view if user is authenticated
    tv_user = get_tv_user()
    if tv_user:
        db.execute(
            'INSERT OR IGNORE INTO video_views (video_id, user_id, view_date) VALUES (?, ?, ?)',
            (video_id, tv_user['id'], int(time.time()))
        )
        db.commit()
    
    return jsonify(dict(video))

@tv_api.route('/videos/search')
def search_videos():
    """Search videos with TV-friendly results."""
    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)
    offset = int(request.args.get('offset', 0))
    
    if not query:
        return jsonify({'videos': [], 'has_more': False})
    
    search_term = f"%{query}%"
    db = get_db()
    videos = db.execute(
        '''SELECT v.id, v.title, v.description, v.thumbnail_url, v.video_url,
                  v.duration, v.upload_date, u.username as uploader
           FROM videos v
           JOIN users u ON v.user_id = u.id
           WHERE v.is_processed = 1 AND (v.title LIKE ? OR v.description LIKE ?)
           ORDER BY v.upload_date DESC
           LIMIT ? OFFSET ?''',
        (search_term, search_term, limit, offset)
    ).fetchall()
    
    return jsonify({
        'videos': [dict(video) for video in videos],
        'has_more': len(videos) == limit,
        'query': query
    })

@tv_api.route('/categories')
def get_categories():
    """Get available video categories."""
    db = get_db()
    categories = db.execute(
        '''SELECT DISTINCT category, COUNT(*) as video_count
           FROM videos 
           WHERE is_processed = 1 AND category IS NOT NULL AND category != ''
           GROUP BY category
           ORDER BY video_count DESC'''
    ).fetchall()
    
    return jsonify([dict(cat) for cat in categories])

@tv_api.route('/categories/<category>/videos')
def category_videos(category):
    """Get videos from a specific category."""
    limit = min(int(request.args.get('limit', 20)), 50)
    offset = int(request.args.get('offset', 0))
    
    db = get_db()
    videos = db.execute(
        '''SELECT v.id, v.title, v.description, v.thumbnail_url, v.video_url,
                  v.duration, v.upload_date, u.username as uploader
           FROM videos v
           JOIN users u ON v.user_id = u.id
           WHERE v.is_processed = 1 AND v.category = ?
           ORDER BY v.upload_date DESC
           LIMIT ? OFFSET ?''',
        (category, limit, offset)
    ).fetchall()
    
    return jsonify({
        'videos': [dict(video) for video in videos],
        'category': category,
        'has_more': len(videos) == limit
    })

@tv_api.route('/user/watchlist')
def get_watchlist():
    """Get user's watchlist (requires authentication)."""
    tv_user = get_tv_user()
    if not tv_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    limit = min(int(request.args.get('limit', 20)), 50)
    offset = int(request.args.get('offset', 0))
    
    db = get_db()
    videos = db.execute(
        '''SELECT v.id, v.title, v.description, v.thumbnail_url, v.video_url,
                  v.duration, v.upload_date, u.username as uploader, w.added_date
           FROM watchlist w
           JOIN videos v ON w.video_id = v.id
           JOIN users u ON v.user_id = u.id
           WHERE w.user_id = ? AND v.is_processed = 1
           ORDER BY w.added_date DESC
           LIMIT ? OFFSET ?''',
        (tv_user['id'], limit, offset)
    ).fetchall()
    
    return jsonify({
        'videos': [dict(video) for video in videos],
        'has_more': len(videos) == limit
    })