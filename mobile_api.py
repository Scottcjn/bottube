# SPDX-License-Identifier: MIT
from flask import Blueprint, request, jsonify, g, session
import sqlite3
import bcrypt
import jwt
import datetime
import os
from functools import wraps
from bottube_server import get_db

mobile_api = Blueprint('mobile_api', __name__, url_prefix='/api/mobile')


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            if token.startswith('Bearer '):
                token = token[7:]
            jwt_secret = os.environ['JWT_SECRET']
            data = jwt.decode(token, jwt_secret, algorithms=['HS256'])
            g.user_id = data['user_id']
            g.username = data['username']
        except (jwt.InvalidTokenError, KeyError):
            return jsonify({'error': 'Token is invalid'}), 401

        return f(*args, **kwargs)
    return decorated


@mobile_api.route('/auth/login', methods=['POST'])
def mobile_login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

    if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        try:
            jwt_secret = os.environ['JWT_SECRET']
            token = jwt.encode({
                'user_id': user['id'],
                'username': user['username'],
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)
            }, jwt_secret, algorithm='HS256')

            return jsonify({
                'token': token,
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'email': user.get('email', ''),
                    'joined': user.get('joined', '')
                }
            }), 200
        except KeyError:
            return jsonify({'error': 'Server configuration error'}), 500
    else:
        return jsonify({'error': 'Invalid credentials'}), 401


@mobile_api.route('/auth/register', methods=['POST'])
def mobile_register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    username = data.get('username')
    password = data.get('password')
    email = data.get('email')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    # Validate password strength
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    db = get_db()

    # Check if user exists
    existing_user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if existing_user:
        return jsonify({'error': 'Username already exists'}), 409

    # Hash password with bcrypt
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        db.execute(
            'INSERT INTO users (username, password, email, joined) VALUES (?, ?, ?, ?)',
            (username, password_hash, email or '', datetime.datetime.now().isoformat())
        )
        db.commit()

        # Generate token for new user
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        jwt_secret = os.environ['JWT_SECRET']
        token = jwt.encode({
            'user_id': user['id'],
            'username': user['username'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)
        }, jwt_secret, algorithm='HS256')

        return jsonify({
            'token': token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user.get('email', ''),
                'joined': user.get('joined', '')
            }
        }), 201
    except KeyError:
        return jsonify({'error': 'Server configuration error'}), 500
    except Exception as e:
        return jsonify({'error': 'Registration failed'}), 500


@mobile_api.route('/videos', methods=['GET'])
@token_required
def get_videos():
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', 20)), 50)  # Cap at 50
    search = request.args.get('search', '')

    offset = (page - 1) * limit

    db = get_db()

    if search:
        query = '''
            SELECT id, title, description, creator, views, upload_date, thumbnail
            FROM videos
            WHERE title LIKE ? OR description LIKE ? OR creator LIKE ?
            ORDER BY upload_date DESC
            LIMIT ? OFFSET ?
        '''
        params = (f'%{search}%', f'%{search}%', f'%{search}%', limit, offset)
    else:
        query = '''
            SELECT id, title, description, creator, views, upload_date, thumbnail
            FROM videos
            ORDER BY upload_date DESC
            LIMIT ? OFFSET ?
        '''
        params = (limit, offset)

    videos = db.execute(query, params).fetchall()

    return jsonify({
        'videos': [dict(video) for video in videos],
        'page': page,
        'limit': limit,
        'has_more': len(videos) == limit
    }), 200


@mobile_api.route('/videos/<int:video_id>', methods=['GET'])
@token_required
def get_video_detail(video_id):
    db = get_db()
    video = db.execute(
        'SELECT * FROM videos WHERE id = ?', (video_id,)
    ).fetchone()

    if not video:
        return jsonify({'error': 'Video not found'}), 404

    # Get comments for this video
    comments = db.execute(
        'SELECT * FROM comments WHERE video_id = ? ORDER BY created_at DESC LIMIT 50',
        (video_id,)
    ).fetchall()

    return jsonify({
        'video': dict(video),
        'comments': [dict(comment) for comment in comments]
    }), 200


@mobile_api.route('/videos/<int:video_id>/comments', methods=['POST'])
@token_required
def add_comment(video_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    content = data.get('content', '').strip()
    if not content:
        return jsonify({'error': 'Comment content required'}), 400

    if len(content) > 1000:
        return jsonify({'error': 'Comment too long (max 1000 characters)'}), 400

    db = get_db()

    # Check if video exists
    video = db.execute('SELECT id FROM videos WHERE id = ?', (video_id,)).fetchone()
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    try:
        cursor = db.execute(
            'INSERT INTO comments (video_id, user_id, username, content, created_at) VALUES (?, ?, ?, ?, ?)',
            (video_id, g.user_id, g.username, content, datetime.datetime.now().isoformat())
        )
        db.commit()

        return jsonify({
            'id': cursor.lastrowid,
            'content': content,
            'username': g.username,
            'created_at': datetime.datetime.now().isoformat()
        }), 201
    except Exception as e:
        return jsonify({'error': 'Failed to add comment'}), 500


@mobile_api.route('/user/profile', methods=['GET'])
@token_required
def get_user_profile():
    db = get_db()
    user = db.execute(
        'SELECT id, username, email, joined FROM users WHERE id = ?',
        (g.user_id,)
    ).fetchone()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Get user's video count
    video_count = db.execute(
        'SELECT COUNT(*) as count FROM videos WHERE creator = ?',
        (user['username'],)
    ).fetchone()['count']

    return jsonify({
        'user': dict(user),
        'video_count': video_count
    }), 200
