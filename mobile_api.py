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
            jwt_secret = os.environ.get('JWT_SECRET', 'fallback-secret-key')
            data = jwt.decode(token, jwt_secret, algorithms=['HS256'])
            g.user_id = data['user_id']
            g.username = data['username']
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token is invalid'}), 401

        return f(*args, **kwargs)
    return decorated


@mobile_api.route('/auth/login', methods=['POST'])
def mobile_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

    if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        jwt_secret = os.environ.get('JWT_SECRET', 'fallback-secret-key')
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

    return jsonify({'error': 'Invalid credentials'}), 401


@mobile_api.route('/auth/register', methods=['POST'])
def mobile_register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')

    if not username or not password or not email:
        return jsonify({'error': 'Username, password, and email required'}), 400

    db = get_db()

    # Check if user exists
    existing_user = db.execute('SELECT * FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
    if existing_user:
        return jsonify({'error': 'Username or email already exists'}), 409

    # Hash password with bcrypt
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    try:
        db.execute('INSERT INTO users (username, password, email, rtc_balance) VALUES (?, ?, ?, ?)',
                  (username, hashed_password.decode('utf-8'), email, 0))
        db.commit()

        # Get the new user
        new_user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        jwt_secret = os.environ.get('JWT_SECRET', 'fallback-secret-key')
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
                'email': new_user['email'],
                'rtc_balance': new_user['rtc_balance']
            }
        }), 201

    except sqlite3.Error:
        return jsonify({'error': 'Registration failed'}), 500


@mobile_api.route('/videos', methods=['GET'])
@token_required
def get_videos():
    db = get_db()
    videos = db.execute('SELECT * FROM videos ORDER BY created_at DESC LIMIT 50').fetchall()

    video_list = []
    for video in videos:
        video_list.append({
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'thumbnail_url': video.get('thumbnail_url'),
            'video_url': video.get('video_url'),
            'views': video.get('views', 0),
            'likes': video.get('likes', 0),
            'created_at': video['created_at']
        })

    return jsonify({'videos': video_list})


@mobile_api.route('/videos/<int:video_id>', methods=['GET'])
@token_required
def get_video(video_id):
    db = get_db()
    video = db.execute('SELECT * FROM videos WHERE id = ?', (video_id,)).fetchone()

    if not video:
        return jsonify({'error': 'Video not found'}), 404

    return jsonify({
        'id': video['id'],
        'title': video['title'],
        'description': video['description'],
        'thumbnail_url': video.get('thumbnail_url'),
        'video_url': video.get('video_url'),
        'views': video.get('views', 0),
        'likes': video.get('likes', 0),
        'created_at': video['created_at']
    })


@mobile_api.route('/profile', methods=['GET'])
@token_required
def get_profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (g.user_id,)).fetchone()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'email': user['email'],
        'rtc_balance': user.get('rtc_balance', 0)
    })


@mobile_api.route('/profile', methods=['PUT'])
@token_required
def update_profile():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    db = get_db()

    try:
        db.execute('UPDATE users SET email = ? WHERE id = ?', (email, g.user_id))
        db.commit()

        updated_user = db.execute('SELECT * FROM users WHERE id = ?', (g.user_id,)).fetchone()

        return jsonify({
            'id': updated_user['id'],
            'username': updated_user['username'],
            'email': updated_user['email'],
            'rtc_balance': updated_user.get('rtc_balance', 0)
        })

    except sqlite3.Error:
        return jsonify({'error': 'Profile update failed'}), 500
