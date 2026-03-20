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
                    'email': user.get('email', '')
                }
            })
        except KeyError:
            return jsonify({'error': 'JWT_SECRET environment variable not set'}), 500
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

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    db = get_db()

    # Check if username exists
    existing_user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if existing_user:
        return jsonify({'error': 'Username already exists'}), 409

    # Hash password with bcrypt
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        db.execute(
            'INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
            (username, password_hash, email or '')
        )
        db.commit()

        # Get the new user
        new_user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        # Generate token
        jwt_secret = os.environ['JWT_SECRET']
        token = jwt.encode({
            'user_id': new_user['id'],
            'username': new_user['username'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)
        }, jwt_secret, algorithm='HS256')

        return jsonify({
            'token': token,
            'user': {
                'id': new_user['id'],
                'username': new_user['username'],
                'email': new_user.get('email', '')
            }
        }), 201
    except KeyError:
        return jsonify({'error': 'JWT_SECRET environment variable not set'}), 500
    except sqlite3.Error as e:
        return jsonify({'error': 'Registration failed'}), 500


@mobile_api.route('/videos', methods=['GET'])
@token_required
def get_videos():
    db = get_db()

    # Get query parameters
    page = max(1, int(request.args.get('page', 1)))
    limit = min(50, max(1, int(request.args.get('limit', 20))))
    search = request.args.get('search', '').strip()

    offset = (page - 1) * limit

    if search:
        videos = db.execute(
            'SELECT * FROM videos WHERE title LIKE ? OR description LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (f'%{search}%', f'%{search}%', limit, offset)
        ).fetchall()

        total = db.execute(
            'SELECT COUNT(*) as count FROM videos WHERE title LIKE ? OR description LIKE ?',
            (f'%{search}%', f'%{search}%')
        ).fetchone()['count']
    else:
        videos = db.execute(
            'SELECT * FROM videos ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (limit, offset)
        ).fetchall()

        total = db.execute('SELECT COUNT(*) as count FROM videos').fetchone()['count']

    return jsonify({
        'videos': [dict(video) for video in videos],
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': (total + limit - 1) // limit
        }
    })


@mobile_api.route('/videos/<int:video_id>', methods=['GET'])
@token_required
def get_video(video_id):
    db = get_db()
    video = db.execute('SELECT * FROM videos WHERE id = ?', (video_id,)).fetchone()

    if not video:
        return jsonify({'error': 'Video not found'}), 404

    return jsonify({'video': dict(video)})


@mobile_api.route('/videos/<int:video_id>/like', methods=['POST'])
@token_required
def like_video(video_id):
    db = get_db()

    # Check if video exists
    video = db.execute('SELECT id FROM videos WHERE id = ?', (video_id,)).fetchone()
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    # Check if already liked
    existing_like = db.execute(
        'SELECT id FROM video_likes WHERE user_id = ? AND video_id = ?',
        (g.user_id, video_id)
    ).fetchone()

    if existing_like:
        return jsonify({'error': 'Already liked'}), 409

    try:
        db.execute(
            'INSERT INTO video_likes (user_id, video_id, created_at) VALUES (?, ?, ?)',
            (g.user_id, video_id, datetime.datetime.now())
        )
        db.commit()

        # Get updated like count
        like_count = db.execute(
            'SELECT COUNT(*) as count FROM video_likes WHERE video_id = ?',
            (video_id,)
        ).fetchone()['count']

        return jsonify({
            'message': 'Video liked successfully',
            'like_count': like_count
        })
    except sqlite3.Error:
        return jsonify({'error': 'Failed to like video'}), 500


@mobile_api.route('/profile', methods=['GET'])
@token_required
def get_profile():
    db = get_db()
    user = db.execute(
        'SELECT id, username, email, created_at FROM users WHERE id = ?',
        (g.user_id,)
    ).fetchone()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Get user's video count
    video_count = db.execute(
        'SELECT COUNT(*) as count FROM videos WHERE uploader_id = ?',
        (g.user_id,)
    ).fetchone()['count']

    return jsonify({
        'user': dict(user),
        'stats': {
            'video_count': video_count
        }
    })
