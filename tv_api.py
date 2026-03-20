from flask import Blueprint, jsonify, request, g
from database import get_db
import sqlite3
from datetime import datetime, timedelta

tv_api = Blueprint('tv_api', __name__, url_prefix='/api/tv')

def get_video_data_for_tv(video_row):
    """Convert video row to TV-friendly format with large thumbnails"""
    return {
        'id': video_row['id'],
        'title': video_row['title'],
        'description': video_row['description'][:200] + '...' if len(video_row['description']) > 200 else video_row['description'],
        'thumbnail_url': video_row['thumbnail_url'],
        'video_url': video_row['video_url'],
        'duration': video_row.get('duration', 0),
        'view_count': video_row.get('view_count', 0),
        'created_at': video_row['created_at'],
        'channel_name': video_row.get('channel_name', 'BoTTube'),
        'category': video_row.get('category', 'general')
    }

@tv_api.route('/trending')
def get_trending_videos():
    """Get trending videos optimized for TV browsing"""
    try:
        db = get_db()
        cursor = db.cursor()

        # Get videos with highest view counts from last 7 days
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('''
            SELECT v.*, u.username as channel_name
            FROM videos v
            LEFT JOIN users u ON v.user_id = u.id
            WHERE v.created_at >= ?
            ORDER BY v.view_count DESC, v.created_at DESC
            LIMIT 20
        ''', (week_ago,))

        videos = cursor.fetchall()

        tv_videos = []
        for video in videos:
            video_dict = dict(video)
            tv_videos.append(get_video_data_for_tv(video_dict))

        return jsonify({
            'success': True,
            'videos': tv_videos,
            'total': len(tv_videos)
        })

    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@tv_api.route('/categories')
def get_categories():
    """Get available video categories for TV navigation"""
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            SELECT category, COUNT(*) as count
            FROM videos
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category
            ORDER BY count DESC
        ''')

        categories = cursor.fetchall()

        category_list = []
        for cat in categories:
            category_list.append({
                'name': cat['category'],
                'count': cat['count'],
                'display_name': cat['category'].title()
            })

        return jsonify({
            'success': True,
            'categories': category_list
        })

    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@tv_api.route('/category/<category_name>')
def get_category_videos(category_name):
    """Get videos from a specific category"""
    try:
        db = get_db()
        cursor = db.cursor()

        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 12))
        offset = (page - 1) * limit

        cursor.execute('''
            SELECT v.*, u.username as channel_name
            FROM videos v
            LEFT JOIN users u ON v.user_id = u.id
            WHERE v.category = ?
            ORDER BY v.created_at DESC
            LIMIT ? OFFSET ?
        ''', (category_name, limit, offset))

        videos = cursor.fetchall()

        tv_videos = []
        for video in videos:
            video_dict = dict(video)
            tv_videos.append(get_video_data_for_tv(video_dict))

        return jsonify({
            'success': True,
            'videos': tv_videos,
            'category': category_name,
            'page': page,
            'limit': limit
        })

    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@tv_api.route('/search')
def search_videos():
    """Search videos with TV-optimized results"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'success': False, 'error': 'Search query required'}), 400

    try:
        db = get_db()
        cursor = db.cursor()

        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 12))
        offset = (page - 1) * limit

        search_term = f'%{query}%'

        cursor.execute('''
            SELECT v.*, u.username as channel_name
            FROM videos v
            LEFT JOIN users u ON v.user_id = u.id
            WHERE v.title LIKE ? OR v.description LIKE ?
            ORDER BY v.view_count DESC, v.created_at DESC
            LIMIT ? OFFSET ?
        ''', (search_term, search_term, limit, offset))

        videos = cursor.fetchall()

        tv_videos = []
        for video in videos:
            video_dict = dict(video)
            tv_videos.append(get_video_data_for_tv(video_dict))

        return jsonify({
            'success': True,
            'videos': tv_videos,
            'query': query,
            'page': page,
            'limit': limit,
            'total': len(tv_videos)
        })

    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@tv_api.route('/recent')
def get_recent_videos():
    """Get recently uploaded videos for TV home screen"""
    try:
        db = get_db()
        cursor = db.cursor()

        limit = int(request.args.get('limit', 20))

        cursor.execute('''
            SELECT v.*, u.username as channel_name
            FROM videos v
            LEFT JOIN users u ON v.user_id = u.id
            ORDER BY v.created_at DESC
            LIMIT ?
        ''', (limit,))

        videos = cursor.fetchall()

        tv_videos = []
        for video in videos:
            video_dict = dict(video)
            tv_videos.append(get_video_data_for_tv(video_dict))

        return jsonify({
            'success': True,
            'videos': tv_videos,
            'total': len(tv_videos)
        })

    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@tv_api.route('/video/<int:video_id>')
def get_video_details(video_id):
    """Get detailed video information for TV playback"""
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            SELECT v.*, u.username as channel_name
            FROM videos v
            LEFT JOIN users u ON v.user_id = u.id
            WHERE v.id = ?
        ''', (video_id,))

        video = cursor.fetchone()

        if not video:
            return jsonify({'success': False, 'error': 'Video not found'}), 404

        video_dict = dict(video)
        tv_video = get_video_data_for_tv(video_dict)

        # Get related videos from same category
        cursor.execute('''
            SELECT v.*, u.username as channel_name
            FROM videos v
            LEFT JOIN users u ON v.user_id = u.id
            WHERE v.category = ? AND v.id != ?
            ORDER BY v.view_count DESC
            LIMIT 8
        ''', (video_dict.get('category', ''), video_id))

        related_videos = cursor.fetchall()
        related_tv_videos = []
        for related in related_videos:
            related_dict = dict(related)
            related_tv_videos.append(get_video_data_for_tv(related_dict))

        return jsonify({
            'success': True,
            'video': tv_video,
            'related_videos': related_tv_videos
        })

    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@tv_api.route('/featured')
def get_featured_content():
    """Get featured content for TV home screen carousel"""
    try:
        db = get_db()
        cursor = db.cursor()

        # Get top videos with good thumbnails for featured carousel
        cursor.execute('''
            SELECT v.*, u.username as channel_name
            FROM videos v
            LEFT JOIN users u ON v.user_id = u.id
            WHERE v.thumbnail_url IS NOT NULL AND v.thumbnail_url != ''
            ORDER BY v.view_count DESC, v.created_at DESC
            LIMIT 6
        ''')

        videos = cursor.fetchall()

        featured_videos = []
        for video in videos:
            video_dict = dict(video)
            tv_video = get_video_data_for_tv(video_dict)
            tv_video['featured'] = True
            featured_videos.append(tv_video)

        return jsonify({
            'success': True,
            'featured_videos': featured_videos
        })

    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
