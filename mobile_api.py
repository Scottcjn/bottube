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
        except:
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
    existing = db.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
    
    if existing:
        return jsonify({'error': 'Username or email already exists'}), 400
    
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    try:
        db.execute(
            'INSERT INTO users (username, password, email, rtc_balance) VALUES (?, ?, ?, 0)',
            (username, hashed_password, email)
        )
        db.commit()
        
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
                'rtc_balance': 0
            }
        })
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Registration failed'}), 500

@mobile_api.route('/videos', methods=['GET'])
def get_videos():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    search = request.args.get('search', '')
    
    offset = (page - 1) * limit
    
    if search:
        videos = db.execute('''
            SELECT v.*, u.username as uploader 
            FROM videos v 
            JOIN users u ON v.user_id = u.id 
            WHERE v.title LIKE ? OR v.description LIKE ?
            ORDER BY v.created_at DESC 
            LIMIT ? OFFSET ?
        ''', (f'%{search}%', f'%{search}%', limit, offset)).fetchall()
    else:
        videos = db.execute('''
            SELECT v.*, u.username as uploader 
            FROM videos v 
            JOIN users u ON v.user_id = u.id 
            ORDER BY v.created_at DESC 
            LIMIT ? OFFSET ?
        ''', (limit, offset)).fetchall()
    
    video_list = []
    for video in videos:
        likes = db.execute('SELECT COUNT(*) FROM likes WHERE video_id = ?', (video['id'],)).fetchone()[0]
        views = db.execute('SELECT view_count FROM video_stats WHERE video_id = ?', (video['id'],)).fetchone()
        view_count = views[0] if views else 0
        
        video_list.append({
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'thumbnail_url': video.get('thumbnail_url'),
            'duration': video.get('duration'),
            'uploader': video['uploader'],
            'created_at': video['created_at'],
            'likes': likes,
            'views': view_count
        })
    
    return jsonify({'videos': video_list})

@mobile_api.route('/videos/<int:video_id>', methods=['GET'])
def get_video_details(video_id):
    db = get_db()
    
    video = db.execute('''
        SELECT v.*, u.username as uploader, u.id as uploader_id
        FROM videos v 
        JOIN users u ON v.user_id = u.id 
        WHERE v.id = ?
    ''', (video_id,)).fetchone()
    
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    likes = db.execute('SELECT COUNT(*) FROM likes WHERE video_id = ?', (video_id,)).fetchone()[0]
    views = db.execute('SELECT view_count FROM video_stats WHERE video_id = ?', (video_id,)).fetchone()
    view_count = views[0] if views else 0
    
    # Increment view count
    if views:
        db.execute('UPDATE video_stats SET view_count = view_count + 1 WHERE video_id = ?', (video_id,))
    else:
        db.execute('INSERT INTO video_stats (video_id, view_count) VALUES (?, 1)', (video_id,))
    db.commit()
    
    comments = db.execute('''
        SELECT c.*, u.username 
        FROM comments c 
        JOIN users u ON c.user_id = u.id 
        WHERE c.video_id = ? 
        ORDER BY c.created_at DESC
    ''', (video_id,)).fetchall()
    
    comment_list = []
    for comment in comments:
        comment_list.append({
            'id': comment['id'],
            'content': comment['content'],
            'username': comment['username'],
            'created_at': comment['created_at']
        })
    
    return jsonify({
        'id': video['id'],
        'title': video['title'],
        'description': video['description'],
        'video_url': video.get('video_url'),
        'thumbnail_url': video.get('thumbnail_url'),
        'duration': video.get('duration'),
        'uploader': video['uploader'],
        'uploader_id': video['uploader_id'],
        'created_at': video['created_at'],
        'likes': likes,
        'views': view_count + 1,
        'comments': comment_list
    })

@mobile_api.route('/videos/<int:video_id>/like', methods=['POST'])
@token_required
def like_video(video_id):
    db = get_db()
    
    existing = db.execute('SELECT id FROM likes WHERE user_id = ? AND video_id = ?', 
                         (g.user_id, video_id)).fetchone()
    
    if existing:
        db.execute('DELETE FROM likes WHERE user_id = ? AND video_id = ?', 
                  (g.user_id, video_id))
        liked = False
    else:
        db.execute('INSERT INTO likes (user_id, video_id) VALUES (?, ?)', 
                  (g.user_id, video_id))
        liked = True
    
    db.commit()
    
    likes_count = db.execute('SELECT COUNT(*) FROM likes WHERE video_id = ?', (video_id,)).fetchone()[0]
    
    return jsonify({'liked': liked, 'likes_count': likes_count})

@mobile_api.route('/videos/<int:video_id>/comments', methods=['POST'])
@token_required
def add_comment(video_id):
    data = request.get_json()
    content = data.get('content', '').strip()
    
    if not content:
        return jsonify({'error': 'Comment content required'}), 400
    
    db = get_db()
    
    db.execute(
        'INSERT INTO comments (user_id, video_id, content) VALUES (?, ?, ?)',
        (g.user_id, video_id, content)
    )
    db.commit()
    
    comment_id = db.lastrowid
    comment = db.execute('''
        SELECT c.*, u.username 
        FROM comments c 
        JOIN users u ON c.user_id = u.id 
        WHERE c.id = ?
    ''', (comment_id,)).fetchone()
    
    return jsonify({
        'id': comment['id'],
        'content': comment['content'],
        'username': comment['username'],
        'created_at': comment['created_at']
    })

@mobile_api.route('/users/<int:user_id>/subscribe', methods=['POST'])
@token_required
def subscribe_to_user(user_id):
    if g.user_id == user_id:
        return jsonify({'error': 'Cannot subscribe to yourself'}), 400
    
    db = get_db()
    
    existing = db.execute('SELECT id FROM subscriptions WHERE subscriber_id = ? AND channel_id = ?', 
                         (g.user_id, user_id)).fetchone()
    
    if existing:
        db.execute('DELETE FROM subscriptions WHERE subscriber_id = ? AND channel_id = ?', 
                  (g.user_id, user_id))
        subscribed = False
    else:
        db.execute('INSERT INTO subscriptions (subscriber_id, channel_id) VALUES (?, ?)', 
                  (g.user_id, user_id))
        subscribed = True
    
    db.commit()
    
    subscriber_count = db.execute('SELECT COUNT(*) FROM subscriptions WHERE channel_id = ?', (user_id,)).fetchone()[0]
    
    return jsonify({'subscribed': subscribed, 'subscriber_count': subscriber_count})

@mobile_api.route('/users/<username>', methods=['GET'])
def get_user_profile(username):
    db = get_db()
    
    user = db.execute('SELECT id, username, email FROM users WHERE username = ?', (username,)).fetchone()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    videos = db.execute('''
        SELECT id, title, thumbnail_url, created_at 
        FROM videos 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (user['id'],)).fetchall()
    
    subscriber_count = db.execute('SELECT COUNT(*) FROM subscriptions WHERE channel_id = ?', (user['id'],)).fetchone()[0]
    
    video_list = []
    for video in videos:
        video_list.append({
            'id': video['id'],
            'title': video['title'],
            'thumbnail_url': video.get('thumbnail_url'),
            'created_at': video['created_at']
        })
    
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'subscriber_count': subscriber_count,
        'videos': video_list
    })

@mobile_api.route('/user/subscriptions', methods=['GET'])
@token_required
def get_subscriptions():
    db = get_db()
    
    subscriptions = db.execute('''
        SELECT u.id, u.username 
        FROM subscriptions s 
        JOIN users u ON s.channel_id = u.id 
        WHERE s.subscriber_id = ?
    ''', (g.user_id,)).fetchall()
    
    sub_list = []
    for sub in subscriptions:
        sub_list.append({
            'id': sub['id'],
            'username': sub['username']
        })
    
    return jsonify({'subscriptions': sub_list})

@mobile_api.route('/user/feed', methods=['GET'])
@token_required
def get_subscription_feed():
    db = get_db()
    
    feed_videos = db.execute('''
        SELECT v.*, u.username as uploader 
        FROM videos v 
        JOIN users u ON v.user_id = u.id 
        JOIN subscriptions s ON s.channel_id = u.id 
        WHERE s.subscriber_id = ? 
        ORDER BY v.created_at DESC 
        LIMIT 50
    ''', (g.user_id,)).fetchall()
    
    video_list = []
    for video in feed_videos:
        likes = db.execute('SELECT COUNT(*) FROM likes WHERE video_id = ?', (video['id'],)).fetchone()[0]
        views = db.execute('SELECT view_count FROM video_stats WHERE video_id = ?', (video['id'],)).fetchone()
        view_count = views[0] if views else 0
        
        video_list.append({
            'id': video['id'],
            'title': video['title'],
            'description': video['description'],
            'thumbnail_url': video.get('thumbnail_url'),
            'duration': video.get('duration'),
            'uploader': video['uploader'],
            'created_at': video['created_at'],
            'likes': likes,
            'views': view_count
        })
    
    return jsonify({'videos': video_list})

@mobile_api.route('/user/profile', methods=['GET'])
@token_required
def get_user_account():
    db = get_db()
    
    user = db.execute('SELECT * FROM users WHERE id = ?', (g.user_id,)).fetchone()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    videos = db.execute('SELECT COUNT(*) FROM videos WHERE user_id = ?', (g.user_id,)).fetchone()[0]
    subscribers = db.execute('SELECT COUNT(*) FROM subscriptions WHERE channel_id = ?', (g.user_id,)).fetchone()[0]
    
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'email': user['email'],
        'rtc_balance': user.get('rtc_balance', 0),
        'video_count': videos,
        'subscriber_count': subscribers
    })

@mobile_api.route('/search', methods=['GET'])
def search_content():
    query = request.args.get('q', '').strip()
    type_filter = request.args.get('type', 'all')
    
    if not query:
        return jsonify({'videos': [], 'users': []})
    
    db = get_db()
    results = {'videos': [], 'users': []}
    
    if type_filter in ['all', 'videos']:
        videos = db.execute('''
            SELECT v.*, u.username as uploader 
            FROM videos v 
            JOIN users u ON v.user_id = u.id 
            WHERE v.title LIKE ? OR v.description LIKE ?
            ORDER BY v.created_at DESC 
            LIMIT 20
        ''', (f'%{query}%', f'%{query}%')).fetchall()
        
        for video in videos:
            results['videos'].append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'thumbnail_url': video.get('thumbnail_url'),
                'uploader': video['uploader'],
                'created_at': video['created_at']
            })
    
    if type_filter in ['all', 'users']:
        users = db.execute('''
            SELECT id, username 
            FROM users 
            WHERE username LIKE ? 
            LIMIT 10
        ''', (f'%{query}%',)).fetchall()
        
        for user in users:
            subscriber_count = db.execute('SELECT COUNT(*) FROM subscriptions WHERE channel_id = ?', (user['id'],)).fetchone()[0]
            results['users'].append({
                'id': user['id'],
                'username': user['username'],
                'subscriber_count': subscriber_count
            })
    
    return jsonify(results)