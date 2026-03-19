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
    password = data.get('password')
    email = data.get('email')
    
    if not username or not password or not email:
        return jsonify({'error': 'Username, password and email required'}), 400
    
    db = get_db()
    
    # Check if user exists
    existing_user = db.execute('SELECT id FROM users WHERE username = ? OR email = ?', 
                              (username, email)).fetchone()
    if existing_user:
        return jsonify({'error': 'User already exists'}), 409
    
    # Create new user
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    try:
        db.execute('INSERT INTO users (username, password, email, rtc_balance) VALUES (?, ?, ?, ?)',
                  (username, password_hash, email, 0))
        db.commit()
        
        # Generate token
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
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
                'rtc_balance': user['rtc_balance']
            }
        }), 201
    except sqlite3.Error:
        return jsonify({'error': 'Registration failed'}), 500

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
            'rtc_balance': user['rtc_balance']
        }
    })

@mobile_api.route('/videos', methods=['GET'])
@token_required
def get_videos():
    db = get_db()
    videos = db.execute('''
        SELECT v.id, v.title, v.description, v.url, v.created_at, u.username as creator
        FROM videos v
        JOIN users u ON v.user_id = u.id
        ORDER BY v.created_at DESC
        LIMIT 50
    ''').fetchall()
    
    return jsonify({
        'videos': [{
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'url': video['url'],
            'creator': video['creator'],
            'created_at': video['created_at']
        } for video in videos]
    })

@mobile_api.route('/videos/<int:video_id>', methods=['GET'])
@token_required
def get_video(video_id):
    db = get_db()
    video = db.execute('''
        SELECT v.*, u.username as creator
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.id = ?
    ''', (video_id,)).fetchone()
    
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    return jsonify({
        'video': {
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'url': video['url'],
            'creator': video['creator'],
            'created_at': video['created_at']
        }
    })

@mobile_api.route('/rtc/balance', methods=['GET'])
@token_required
def get_rtc_balance():
    db = get_db()
    user = db.execute('SELECT rtc_balance FROM users WHERE id = ?', (g.user_id,)).fetchone()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({'rtc_balance': user['rtc_balance']})