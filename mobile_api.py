from flask import Blueprint, request, jsonify, g, session
import sqlite3
import hashlib
import jwt
import datetime
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
            data = jwt.decode(token, 'your-secret-key', algorithms=['HS256'])
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

    if user and user['password'] == hashlib.sha256(password.encode()).hexdigest():
        token = jwt.encode({
            'user_id': user['id'],
            'username': user['username'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
        }, 'your-secret-key', algorithm='HS256')

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
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'error': 'Username, email and password required'}), 400

    db = get_db()

    # Check if user already exists
    existing_user = db.execute(
        'SELECT id FROM users WHERE username = ? OR email = ?',
        (username, email)
    ).fetchone()

    if existing_user:
        return jsonify({'error': 'User already exists'}), 409

    # Create new user
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    cursor = db.cursor()
    cursor.execute(
        'INSERT INTO users (username, email, password, rtc_balance) VALUES (?, ?, ?, ?)',
        (username, email, hashed_password, 0)
    )
    db.commit()
    user_id = cursor.lastrowid

    # Generate token
    token = jwt.encode({
        'user_id': user_id,
        'username': username,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }, 'your-secret-key', algorithm='HS256')

    return jsonify({
        'token': token,
        'user': {
            'id': user_id,
            'username': username,
            'email': email,
            'rtc_balance': 0
        }
    }), 201


@mobile_api.route('/videos', methods=['GET'])
@token_required
def get_videos():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    category = request.args.get('category')

    offset = (page - 1) * per_page
    query = 'SELECT * FROM videos'
    params = []

    if category:
        query += ' WHERE category = ?'
        params.append(category)

    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])

    videos = db.execute(query, params).fetchall()

    return jsonify({
        'videos': [dict(video) for video in videos],
        'page': page,
        'per_page': per_page
    })


@mobile_api.route('/videos/<int:video_id>', methods=['GET'])
@token_required
def get_video(video_id):
    db = get_db()
    video = db.execute('SELECT * FROM videos WHERE id = ?', (video_id,)).fetchone()

    if not video:
        return jsonify({'error': 'Video not found'}), 404

    return jsonify({'video': dict(video)})


@mobile_api.route('/user/profile', methods=['GET'])
@token_required
def get_profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (g.user_id,)).fetchone()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'rtc_balance': user.get('rtc_balance', 0),
            'created_at': user.get('created_at')
        }
    })


@mobile_api.route('/user/videos', methods=['GET'])
@token_required
def get_user_videos():
    db = get_db()
    videos = db.execute(
        'SELECT * FROM videos WHERE user_id = ? ORDER BY created_at DESC',
        (g.user_id,)
    ).fetchall()

    return jsonify({
        'videos': [dict(video) for video in videos]
    })


@mobile_api.route('/upload', methods=['POST'])
@token_required
def upload_video():
    # This would handle video upload
    # For now, return a placeholder
    return jsonify({
        'message': 'Video upload endpoint - implementation needed',
        'status': 'placeholder'
    }), 501


@mobile_api.route('/search', methods=['GET'])
@token_required
def search_videos():
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': 'Search query required'}), 400

    db = get_db()
    videos = db.execute(
        'SELECT * FROM videos WHERE title LIKE ? OR description LIKE ? ORDER BY created_at DESC',
        (f'%{query}%', f'%{query}%')
    ).fetchall()

    return jsonify({
        'videos': [dict(video) for video in videos],
        'query': query
    })