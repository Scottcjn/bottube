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

    # Get categories based on tags or create basic categories
    cursor.execute('''
        SELECT DISTINCT COALESCE(v.category, 'General') as category,
               COUNT(*) as video_count
        FROM videos v
        GROUP BY category
        ORDER BY video_count DESC
    ''')
    categories = cursor.fetchall()

    category_list = []
    for row in categories:
        category_list.append({
            'name': row[0],
            'count': row[1]
        })

    return jsonify(category_list)


@tv_bp.route('/trending')
def tv_trending():
    """Get trending videos for TV"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        ORDER BY v.view_count DESC, v.created_at DESC
        LIMIT 50
    ''')
    videos = cursor.fetchall()

    video_list = []
    for row in videos:
        video_list.append({
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'thumbnail_url': row[3],
            'duration': row[4],
            'username': row[5],
            'view_count': row[6],
            'created_at': row[7]
        })

    return jsonify(video_list)


@tv_bp.route('/recent')
def tv_recent():
    """Get recent videos for TV"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        ORDER BY v.created_at DESC
        LIMIT 50
    ''')
    videos = cursor.fetchall()

    video_list = []
    for row in videos:
        video_list.append({
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'thumbnail_url': row[3],
            'duration': row[4],
            'username': row[5],
            'view_count': row[6],
            'created_at': row[7]
        })

    return jsonify(video_list)


@tv_bp.route('/search')
def tv_search():
    """Search videos for TV interface"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.title LIKE ? OR v.description LIKE ?
        ORDER BY v.view_count DESC
        LIMIT 50
    ''', (f'%{query}%', f'%{query}%'))
    videos = cursor.fetchall()

    video_list = []
    for row in videos:
        video_list.append({
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'thumbnail_url': row[3],
            'duration': row[4],
            'username': row[5],
            'view_count': row[6],
            'created_at': row[7]
        })

    return jsonify(video_list)


@tv_bp.route('/')
def tv_interface():
    """Main TV interface page"""
    return render_template('tv_interface.html')


@tv_bp.route('/video/<int:video_id>')
def tv_video_player(video_id):
    """TV video player page"""
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

    video_data = {
        'id': video[0],
        'title': video[1],
        'description': video[2],
        'file_path': video[3],
        'duration': video[4],
        'username': video[5],
        'view_count': video[6],
        'created_at': video[7]
    }

    return render_template('tv_player.html', video=video_data)
