from flask import Blueprint, request, jsonify, session, g
from database import get_db
import sqlite3
import json
from datetime import datetime

tv_bp = Blueprint('tv', __name__, url_prefix='/tv')

@tv_bp.route('/home')
def tv_home():
    """TV home screen with featured content"""
    db = get_db()
    
    # Get trending videos (most viewed in last 7 days)
    trending = db.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.created_at > datetime('now', '-7 days')
        ORDER BY v.view_count DESC
        LIMIT 20
    ''').fetchall()
    
    # Get recent videos
    recent = db.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        ORDER BY v.created_at DESC
        LIMIT 20
    ''').fetchall()
    
    return jsonify({
        'trending': [dict(row) for row in trending],
        'recent': [dict(row) for row in recent]
    })

@tv_bp.route('/categories')
def tv_categories():
    """Get available video categories for TV browsing"""
    db = get_db()
    
    categories = db.execute('''
        SELECT DISTINCT category, COUNT(*) as video_count
        FROM videos
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY video_count DESC
    ''').fetchall()
    
    return jsonify({
        'categories': [dict(row) for row in categories]
    })

@tv_bp.route('/category/<category>')
def tv_category_videos(category):
    """Get videos by category for TV interface"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit
    
    db = get_db()
    
    videos = db.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.category = ?
        ORDER BY v.created_at DESC
        LIMIT ? OFFSET ?
    ''', (category, limit, offset)).fetchall()
    
    total_count = db.execute('''
        SELECT COUNT(*) FROM videos WHERE category = ?
    ''', (category,)).fetchone()[0]
    
    return jsonify({
        'videos': [dict(row) for row in videos],
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total_count,
            'has_next': (page * limit) < total_count
        }
    })

@tv_bp.route('/search')
def tv_search():
    """Search videos for TV interface"""
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit
    
    if not query:
        return jsonify({'error': 'Search query required'}), 400
    
    db = get_db()
    
    videos = db.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.title LIKE ? OR v.description LIKE ?
        ORDER BY v.view_count DESC
        LIMIT ? OFFSET ?
    ''', (f'%{query}%', f'%{query}%', limit, offset)).fetchall()
    
    total_count = db.execute('''
        SELECT COUNT(*)
        FROM videos v
        WHERE v.title LIKE ? OR v.description LIKE ?
    ''', (f'%{query}%', f'%{query}%')).fetchone()[0]
    
    return jsonify({
        'videos': [dict(row) for row in videos],
        'query': query,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total_count,
            'has_next': (page * limit) < total_count
        }
    })

@tv_bp.route('/video/<int:video_id>')
def tv_video_details(video_id):
    """Get video details optimized for TV playback"""
    db = get_db()
    
    video = db.execute('''
        SELECT v.*, u.username, u.profile_image
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.id = ?
    ''', (video_id,)).fetchone()
    
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    # Get related videos
    related = db.execute('''
        SELECT v.id, v.title, v.thumbnail_url, v.duration, u.username, v.view_count
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.category = ? AND v.id != ?
        ORDER BY v.view_count DESC
        LIMIT 10
    ''', (video['category'], video_id)).fetchall()
    
    # Update view count
    db.execute('UPDATE videos SET view_count = view_count + 1 WHERE id = ?', (video_id,))
    db.commit()
    
    return jsonify({
        'video': dict(video),
        'related': [dict(row) for row in related]
    })

@tv_bp.route('/video/<int:video_id>/stream')
def tv_video_stream(video_id):
    """Get streaming URL and metadata for TV playback"""
    db = get_db()
    
    video = db.execute('''
        SELECT id, title, video_url, duration
        FROM videos
        WHERE id = ?
    ''', (video_id,)).fetchone()
    
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    return jsonify({
        'stream_url': video['video_url'],
        'title': video['title'],
        'duration': video['duration'],
        'video_id': video['id']
    })

@tv_bp.route('/watchlist', methods=['GET'])
def tv_get_watchlist():
    """Get user's watchlist for TV interface"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    db = get_db()
    
    watchlist = db.execute('''
        SELECT v.id, v.title, v.thumbnail_url, v.duration, u.username, v.view_count
        FROM watchlist w
        JOIN videos v ON w.video_id = v.id
        JOIN users u ON v.user_id = u.id
        WHERE w.user_id = ?
        ORDER BY w.added_at DESC
    ''', (session['user_id'],)).fetchall()
    
    return jsonify({
        'watchlist': [dict(row) for row in watchlist]
    })

@tv_bp.route('/watchlist/<int:video_id>', methods=['POST', 'DELETE'])
def tv_manage_watchlist(video_id):
    """Add or remove video from watchlist via TV interface"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    db = get_db()
    user_id = session['user_id']
    
    if request.method == 'POST':
        try:
            db.execute('''
                INSERT INTO watchlist (user_id, video_id, added_at)
                VALUES (?, ?, ?)
            ''', (user_id, video_id, datetime.now()))
            db.commit()
            return jsonify({'success': True, 'action': 'added'})
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Already in watchlist'}), 400
    
    elif request.method == 'DELETE':
        db.execute('''
            DELETE FROM watchlist
            WHERE user_id = ? AND video_id = ?
        ''', (user_id, video_id))
        db.commit()
        return jsonify({'success': True, 'action': 'removed'})

@tv_bp.route('/device/register', methods=['POST'])
def tv_device_register():
    """Register TV device for authentication"""
    data = request.json
    device_code = data.get('device_code')
    device_name = data.get('device_name', 'TV Device')
    
    if not device_code:
        return jsonify({'error': 'Device code required'}), 400
    
    db = get_db()
    
    # Store device registration
    db.execute('''
        INSERT INTO tv_devices (device_code, device_name, created_at)
        VALUES (?, ?, ?)
    ''', (device_code, device_name, datetime.now()))
    db.commit()
    
    return jsonify({
        'device_code': device_code,
        'verification_url': '/tv/verify',
        'expires_in': 600
    })

@tv_bp.route('/device/poll', methods=['POST'])
def tv_device_poll():
    """Poll for device authentication status"""
    data = request.json
    device_code = data.get('device_code')
    
    if not device_code:
        return jsonify({'error': 'Device code required'}), 400
    
    db = get_db()
    
    device = db.execute('''
        SELECT * FROM tv_devices
        WHERE device_code = ?
    ''', (device_code,)).fetchone()
    
    if not device:
        return jsonify({'error': 'Invalid device code'}), 400
    
    if device['user_id']:
        # Device is authenticated
        return jsonify({
            'access_token': device['access_token'],
            'user_id': device['user_id']
        })
    
    return jsonify({'status': 'pending'}), 202