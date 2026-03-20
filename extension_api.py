from flask import Blueprint, request, jsonify, send_from_directory, g, session
from functools import wraps
import os
import json
import sqlite3
from datetime import datetime, timedelta

extension_bp = Blueprint('extension', __name__)

def get_db():
    """Get database connection"""
    db = sqlite3.connect('bottube.db')
    db.row_factory = sqlite3.Row
    return db

def cors_headers(f):
    """Add CORS headers for extension requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = f(*args, **kwargs)
        if hasattr(response, 'headers'):
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Extension-Id'
        return response
    return decorated_function

def auth_required(f):
    """Require authentication for extension API calls"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
        extension_id = request.headers.get('X-Extension-Id')

        if not api_key or not extension_id:
            return jsonify({'error': 'Authentication required'}), 401

        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE api_key = ?', (api_key,)
        ).fetchone()
        db.close()

        if not user:
            return jsonify({'error': 'Invalid API key'}), 401

        g.user = user
        return f(*args, **kwargs)
    return decorated_function

@extension_bp.route('/extension/manifest.json')
@cors_headers
def manifest():
    """Serve extension manifest"""
    manifest_data = {
        "manifest_version": 3,
        "name": "BoTTube Extension",
        "version": "1.0.0",
        "description": "Browse, vote, and upload to BoTTube from anywhere",
        "permissions": [
            "storage",
            "activeTab",
            "notifications"
        ],
        "host_permissions": [
            "https://bottube.ai/*"
        ],
        "action": {
            "default_popup": "popup.html",
            "default_title": "BoTTube",
            "default_icon": {
                "16": "icons/icon16.png",
                "32": "icons/icon32.png",
                "48": "icons/icon48.png",
                "128": "icons/icon128.png"
            }
        },
        "background": {
            "service_worker": "background.js"
        },
        "content_scripts": [{
            "matches": ["<all_urls>"],
            "js": ["content.js"],
            "run_at": "document_end"
        }],
        "web_accessible_resources": [{
            "resources": ["icons/*", "popup.html"],
            "matches": ["<all_urls>"]
        }]
    }
    return jsonify(manifest_data)

@extension_bp.route('/extension/files/<path:filename>')
@cors_headers
def serve_extension_file(filename):
    """Serve extension static files"""
    extension_dir = os.path.join(os.path.dirname(__file__), 'static', 'extension')
    if os.path.exists(os.path.join(extension_dir, filename)):
        return send_from_directory(extension_dir, filename)
    return jsonify({'error': 'File not found'}), 404

@extension_bp.route('/api/extension/videos/trending')
@cors_headers
def get_trending_videos():
    """Get trending videos for extension popup"""
    db = get_db()
    videos = db.execute('''
        SELECT v.id, v.title, v.thumbnail, v.views, v.likes, v.dislikes,
               u.username as creator, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.created_at > datetime('now', '-7 days')
        ORDER BY (v.likes + v.views) DESC
        LIMIT 20
    ''').fetchall()
    db.close()

    video_list = []
    for video in videos:
        video_list.append({
            'id': video['id'],
            'title': video['title'],
            'thumbnail': video['thumbnail'],
            'creator': video['creator'],
            'views': video['views'],
            'likes': video['likes'],
            'dislikes': video['dislikes'],
            'created_at': video['created_at']
        })

    return jsonify({'videos': video_list})

@extension_bp.route('/api/extension/videos/search')
@cors_headers
def search_videos():
    """Search videos for extension"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'videos': []})

    db = get_db()
    videos = db.execute('''
        SELECT v.id, v.title, v.thumbnail, v.views, v.likes, v.dislikes,
               u.username as creator, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.title LIKE ? OR v.description LIKE ?
        ORDER BY v.created_at DESC
        LIMIT 15
    ''', (f'%{query}%', f'%{query}%')).fetchall()
    db.close()

    video_list = []
    for video in videos:
        video_list.append({
            'id': video['id'],
            'title': video['title'],
            'thumbnail': video['thumbnail'],
            'creator': video['creator'],
            'views': video['views'],
            'likes': video['likes'],
            'dislikes': video['dislikes']
        })

    return jsonify({'videos': video_list})

@extension_bp.route('/api/extension/videos/<int:video_id>/vote', methods=['POST'])
@cors_headers
@auth_required
def vote_on_video(video_id):
    """Vote on a video from extension"""
    data = request.get_json()
    vote_type = data.get('type')

    if vote_type not in ['like', 'dislike']:
        return jsonify({'error': 'Invalid vote type'}), 400

    db = get_db()

    # Check if video exists
    video = db.execute('SELECT * FROM videos WHERE id = ?', (video_id,)).fetchone()
    if not video:
        db.close()
        return jsonify({'error': 'Video not found'}), 404

    # Check existing vote
    existing_vote = db.execute(
        'SELECT * FROM video_votes WHERE user_id = ? AND video_id = ?',
        (g.user['id'], video_id)
    ).fetchone()

    if existing_vote:
        if existing_vote['vote_type'] == vote_type:
            # Remove vote
            db.execute(
                'DELETE FROM video_votes WHERE user_id = ? AND video_id = ?',
                (g.user['id'], video_id)
            )
            # Update video counts
            if vote_type == 'like':
                db.execute('UPDATE videos SET likes = likes - 1 WHERE id = ?', (video_id,))
            else:
                db.execute('UPDATE videos SET dislikes = dislikes - 1 WHERE id = ?', (video_id,))
            vote_status = 'removed'
        else:
            # Change vote
            db.execute(
                'UPDATE video_votes SET vote_type = ? WHERE user_id = ? AND video_id = ?',
                (vote_type, g.user['id'], video_id)
            )
            # Update video counts
            if vote_type == 'like':
                db.execute(
                    'UPDATE videos SET likes = likes + 1, dislikes = dislikes - 1 WHERE id = ?',
                    (video_id,)
                )
            else:
                db.execute(
                    'UPDATE videos SET likes = likes - 1, dislikes = dislikes + 1 WHERE id = ?',
                    (video_id,)
                )
            vote_status = 'changed'
    else:
        # New vote
        db.execute(
            'INSERT INTO video_votes (user_id, video_id, vote_type) VALUES (?, ?, ?)',
            (g.user['id'], video_id, vote_type)
        )
        # Update video counts
        if vote_type == 'like':
            db.execute('UPDATE videos SET likes = likes + 1 WHERE id = ?', (video_id,))
        else:
            db.execute('UPDATE videos SET dislikes = dislikes + 1 WHERE id = ?', (video_id,))
        vote_status = 'added'

    db.commit()

    # Get updated counts
    updated_video = db.execute(
        'SELECT likes, dislikes FROM videos WHERE id = ?', (video_id,)
    ).fetchone()
    db.close()

    return jsonify({
        'status': vote_status,
        'likes': updated_video['likes'],
        'dislikes': updated_video['dislikes']
    })

@extension_bp.route('/api/extension/notifications')
@cors_headers
@auth_required
def get_notifications():
    """Get notification count for extension badge"""
    db = get_db()

    # Count new videos from subscribed channels (if implemented)
    # For now, just count recent videos
    recent_count = db.execute('''
        SELECT COUNT(*) as count FROM videos
        WHERE created_at > datetime('now', '-24 hours')
    ''').fetchone()

    db.close()

    return jsonify({
        'count': recent_count['count'],
        'has_new': recent_count['count'] > 0
    })

@extension_bp.route('/api/extension/user/profile')
@cors_headers
@auth_required
def get_user_profile():
    """Get user profile for extension"""
    return jsonify({
        'username': g.user['username'],
        'email': g.user['email'],
        'created_at': g.user['created_at']
    })

@extension_bp.route('/api/extension/videos/upload', methods=['POST', 'OPTIONS'])
@cors_headers
@auth_required
def upload_video():
    """Handle video upload from extension"""
    if request.method == 'OPTIONS':
        return '', 200

    data = request.get_json()
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    video_url = data.get('video_url', '').strip()

    if not title or not video_url:
        return jsonify({'error': 'Title and video URL required'}), 400

    db = get_db()
    cursor = db.execute('''
        INSERT INTO videos (user_id, title, description, video_url, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (g.user['id'], title, description, video_url, datetime.now().isoformat()))

    video_id = cursor.lastrowid
    db.commit()
    db.close()

    return jsonify({
        'message': 'Video uploaded successfully',
        'video_id': video_id,
        'url': f'/watch/{video_id}'
    })
