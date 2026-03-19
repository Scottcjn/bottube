from flask import Blueprint, request, jsonify, session, g, render_template
from db import get_db
import sqlite3
import json
from datetime import datetime

tv_bp = Blueprint('tv', __name__, url_prefix='/tv')


@tv_bp.route('/home')
def tv_home():
    """TV home screen with featured content"""
    db = get_db()
    cursor = db.cursor()

    # Get trending videos (most viewed in last 7 days)
    cursor.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.created_at > datetime('now', '-7 days')
        ORDER BY v.view_count DESC
        LIMIT 20
    ''')
    trending = cursor.fetchall()

    # Get recent videos
    cursor.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        ORDER BY v.created_at DESC
        LIMIT 20
    ''')
    recent = cursor.fetchall()

    trending_list = []
    for row in trending:
        trending_list.append({
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'thumbnail_url': row[3],
            'duration': row[4],
            'username': row[5],
            'view_count': row[6],
            'created_at': row[7]
        })

    recent_list = []
    for row in recent:
        recent_list.append({
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'thumbnail_url': row[3],
            'duration': row[4],
            'username': row[5],
            'view_count': row[6],
            'created_at': row[7]
        })

    return jsonify({
        'trending': trending_list,
        'recent': recent_list
    })


@tv_bp.route('/categories')
def tv_categories():
    """Get available video categories for TV browsing"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT DISTINCT category, COUNT(*) as video_count
        FROM videos
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY video_count DESC
    ''')
    categories = cursor.fetchall()

    categories_list = []
    for row in categories:
        categories_list.append({
            'category': row[0],
            'video_count': row[1]
        })

    return jsonify({
        'categories': categories_list
    })


@tv_bp.route('/category/<category>')
def tv_category_videos(category):
    """Get videos by category for TV interface"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit

    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.category = ?
        ORDER BY v.view_count DESC, v.created_at DESC
        LIMIT ? OFFSET ?
    ''', (category, limit, offset))
    videos = cursor.fetchall()

    videos_list = []
    for row in videos:
        videos_list.append({
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'thumbnail_url': row[3],
            'duration': row[4],
            'username': row[5],
            'view_count': row[6],
            'created_at': row[7]
        })

    return jsonify({
        'category': category,
        'videos': videos_list,
        'page': page,
        'total': len(videos_list)
    })


@tv_bp.route('/search')
def tv_search():
    """Search videos for TV interface"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit

    if not query:
        return jsonify({
            'query': '',
            'videos': [],
            'total': 0
        })

    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.title LIKE ? OR v.description LIKE ? OR u.username LIKE ?
        ORDER BY v.view_count DESC, v.created_at DESC
        LIMIT ? OFFSET ?
    ''', (f'%{query}%', f'%{query}%', f'%{query}%', limit, offset))
    videos = cursor.fetchall()

    videos_list = []
    for row in videos:
        videos_list.append({
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'thumbnail_url': row[3],
            'duration': row[4],
            'username': row[5],
            'view_count': row[6],
            'created_at': row[7]
        })

    return jsonify({
        'query': query,
        'videos': videos_list,
        'page': page,
        'total': len(videos_list)
    })


@tv_bp.route('/player/<int:video_id>')
def tv_player(video_id):
    """TV video player interface"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT v.id, v.title, v.description, v.file_path, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.id = ?
    ''', (video_id,))
    video = cursor.fetchone()

    if not video:
        return jsonify({'error': 'Video not found'}), 404

    # Increment view count
    cursor.execute('UPDATE videos SET view_count = view_count + 1 WHERE id = ?', (video_id,))
    db.commit()

    video_data = {
        'id': video[0],
        'title': video[1],
        'description': video[2],
        'file_path': video[3],
        'duration': video[4],
        'username': video[5],
        'view_count': video[6] + 1,
        'created_at': video[7]
    }

    return render_template('tv_player.html', video=video_data)


@tv_bp.route('/')
def tv_interface():
    """Main TV interface"""
    return render_template('tv_interface.html')


@tv_bp.route('/remote')
def tv_remote():
    """TV remote control interface for mobile devices"""
    return render_template('tv_remote.html')