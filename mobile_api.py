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
                    'email': user['email'],
                    'rtc_balance': user.get('rtc_balance', 0)
                }
            })
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
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'error': 'Username, email, and password required'}), 400

    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    db = get_db()

    # Check if user already exists
    existing_user = db.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
    if existing_user:
        return jsonify({'error': 'User already exists'}), 409

    # Hash password with bcrypt
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    try:
        db.execute('INSERT INTO users (username, email, password, rtc_balance) VALUES (?, ?, ?, ?)',
                  (username, email, password_hash.decode('utf-8'), 0))
        db.commit()

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
                'email': user['email'],
                'rtc_balance': user.get('rtc_balance', 0)
            }
        }), 201
    except KeyError:
        return jsonify({'error': 'Server configuration error'}), 500
    except sqlite3.Error:
        return jsonify({'error': 'Registration failed'}), 500


@mobile_api.route('/videos', methods=['GET'])
@token_required
def get_videos():
    db = get_db()
    videos = db.execute('''
        SELECT v.*, u.username as creator_username
        FROM videos v
        JOIN users u ON v.creator_id = u.id
        ORDER BY v.upload_date DESC
        LIMIT 20
    ''').fetchall()

    return jsonify({
        'videos': [{
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'creator_username': video['creator_username'],
            'upload_date': video['upload_date'],
            'view_count': video.get('view_count', 0),
            'like_count': video.get('like_count', 0)
        } for video in videos]
    })


@mobile_api.route('/videos/<int:video_id>', methods=['GET'])
@token_required
def get_video(video_id):
    db = get_db()
    video = db.execute('''
        SELECT v.*, u.username as creator_username
        FROM videos v
        JOIN users u ON v.creator_id = u.id
        WHERE v.id = ?
    ''', (video_id,)).fetchone()

    if not video:
        return jsonify({'error': 'Video not found'}), 404

    return jsonify({
        'video': {
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'creator_username': video['creator_username'],
            'upload_date': video['upload_date'],
            'view_count': video.get('view_count', 0),
            'like_count': video.get('like_count', 0)
        }
    })


@mobile_api.route('/videos/<int:video_id>/like', methods=['POST'])
@token_required
def like_video(video_id):
    db = get_db()

    # Check if video exists
    video = db.execute('SELECT id FROM videos WHERE id = ?', (video_id,)).fetchone()
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    # Check if user already liked this video
    existing_like = db.execute('SELECT id FROM video_likes WHERE user_id = ? AND video_id = ?',
                              (g.user_id, video_id)).fetchone()

    if existing_like:
        return jsonify({'error': 'Already liked'}), 409

    try:
        db.execute('INSERT INTO video_likes (user_id, video_id) VALUES (?, ?)',
                  (g.user_id, video_id))
        db.commit()

        # Update like count
        like_count = db.execute('SELECT COUNT(*) as count FROM video_likes WHERE video_id = ?',
                               (video_id,)).fetchone()['count']

        return jsonify({'message': 'Video liked', 'like_count': like_count})
    except sqlite3.Error:
        return jsonify({'error': 'Failed to like video'}), 500


@mobile_api.route('/user/profile', methods=['GET'])
@token_required
def get_profile():
    db = get_db()
    user = db.execute('SELECT id, username, email, rtc_balance FROM users WHERE id = ?',
                     (g.user_id,)).fetchone()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'rtc_balance': user.get('rtc_balance', 0)
        }
    })
