import json
import sqlite3
import math
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from flask import Blueprint, request, jsonify, g
from bottube_server import get_db
from recommendation_engine import RecommendationEngine

recommendations_api = Blueprint('recommendations_api', __name__)
engine = RecommendationEngine()


def calculate_engagement_score(views, likes, comments, upload_date):
    """Calculate engagement score with time decay"""
    if views == 0:
        return 0

    engagement_rate = (likes + comments * 2) / views

    # Time decay factor (newer content gets boost)
    try:
        days_old = (datetime.now() - datetime.fromisoformat(upload_date)).days
        time_factor = math.exp(-days_old / 7.0)  # 7-day half-life
    except (ValueError, TypeError):
        time_factor = 0.5

    return engagement_rate * time_factor * 100


def get_user_watch_history(user_id, limit=50):
    """Get user's recent watch history"""
    db = get_db()
    cursor = db.execute("""
        SELECT DISTINCT v.id, v.title, v.description, v.tags, v.category,
               vh.watched_at, v.upload_date
        FROM view_history vh
        JOIN videos v ON vh.video_id = v.id
        WHERE vh.user_id = ?
        ORDER BY vh.watched_at DESC
        LIMIT ?
    """, (user_id, limit))

    return cursor.fetchall()


def extract_keywords(text):
    """Extract keywords from text for content analysis"""
    if not text:
        return set()

    # Simple keyword extraction - split and filter
    words = text.lower().replace(',', ' ').replace('.', ' ').split()
    # Filter out common words and short words
    stop_words = {
        'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
        'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
        'these', 'those', 'a', 'an'
    }

    keywords = set()
    for word in words:
        if len(word) > 2 and word not in stop_words:
            keywords.add(word)

    return keywords


@recommendations_api.route('/api/recommendations/personalized')
def get_personalized_recommendations():
    """Get personalized recommendations for the current user"""
    user_id = g.get('user', {}).get('id') if hasattr(g, 'user') and g.user else None
    limit = request.args.get('limit', 10, type=int)

    try:
        recommendations = engine.get_personalized_recommendations(user_id, limit)
        return jsonify({
            'success': True,
            'recommendations': [
                {
                    'id': video['id'],
                    'title': video['title'],
                    'description': video['description'],
                    'thumbnail': video.get('thumbnail'),
                    'duration': video.get('duration'),
                    'upload_date': video['upload_date'],
                    'uploader': video.get('uploader'),
                    'category': video.get('category'),
                    'views': video.get('views', 0),
                    'likes': video.get('likes', 0)
                }
                for video in recommendations
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@recommendations_api.route('/api/recommendations/trending')
def get_trending_videos():
    """Get trending videos"""
    limit = request.args.get('limit', 20, type=int)

    try:
        trending = engine.get_trending_videos(limit)
        return jsonify({
            'success': True,
            'videos': [
                {
                    'id': video['id'],
                    'title': video['title'],
                    'description': video['description'],
                    'thumbnail': video.get('thumbnail'),
                    'duration': video.get('duration'),
                    'upload_date': video['upload_date'],
                    'uploader': video.get('uploader'),
                    'category': video.get('category'),
                    'views': video.get('views', 0),
                    'likes': video.get('likes', 0)
                }
                for video in trending
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@recommendations_api.route('/api/recommendations/similar/<int:video_id>')
def get_similar_videos(video_id):
    """Get videos similar to the specified video"""
    limit = request.args.get('limit', 5, type=int)

    try:
        similar = engine.get_similar_videos(video_id, limit)
        return jsonify({
            'success': True,
            'videos': [
                {
                    'id': video['id'],
                    'title': video['title'],
                    'description': video['description'],
                    'thumbnail': video.get('thumbnail'),
                    'duration': video.get('duration'),
                    'upload_date': video['upload_date'],
                    'uploader': video.get('uploader'),
                    'category': video.get('category'),
                    'views': video.get('views', 0)
                }
                for video in similar
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@recommendations_api.route('/api/recommendations/categories')
def get_category_recommendations():
    """Get recommendations by category"""
    category = request.args.get('category')
    limit = request.args.get('limit', 10, type=int)

    if not category:
        return jsonify({'success': False, 'error': 'Category parameter required'}), 400

    try:
        db = get_db()
        videos = db.execute("""
            SELECT v.*, COALESCE(vh.view_count, 0) as views,
                   COALESCE(l.like_count, 0) as likes
            FROM videos v
            LEFT JOIN (
                SELECT video_id, COUNT(*) as view_count
                FROM view_history
                GROUP BY video_id
            ) vh ON v.id = vh.video_id
            LEFT JOIN (
                SELECT video_id, COUNT(*) as like_count
                FROM likes WHERE rating = 'like'
                GROUP BY video_id
            ) l ON v.id = l.video_id
            WHERE v.category = ?
            ORDER BY views DESC, likes DESC
            LIMIT ?
        """, (category, limit)).fetchall()

        return jsonify({
            'success': True,
            'category': category,
            'videos': [
                {
                    'id': video['id'],
                    'title': video['title'],
                    'description': video['description'],
                    'thumbnail': video.get('thumbnail'),
                    'duration': video.get('duration'),
                    'upload_date': video['upload_date'],
                    'uploader': video.get('uploader'),
                    'category': video.get('category'),
                    'views': video.get('views', 0),
                    'likes': video.get('likes', 0)
                }
                for video in videos
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@recommendations_api.route('/api/recommendations/stats')
def get_recommendation_stats():
    """Get recommendation engine statistics"""
    try:
        db = get_db()

        # Get total videos
        total_videos = db.execute("SELECT COUNT(*) as count FROM videos").fetchone()['count']

        # Get categories
        categories = db.execute("""
            SELECT category, COUNT(*) as count
            FROM videos
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
        """).fetchall()

        # Get recent activity
        recent_views = db.execute("""
            SELECT COUNT(*) as count
            FROM view_history
            WHERE created_at > datetime('now', '-24 hours')
        """).fetchone()['count']

        return jsonify({
            'success': True,
            'stats': {
                'total_videos': total_videos,
                'recent_views_24h': recent_views,
                'categories': [
                    {'name': cat['category'], 'count': cat['count']}
                    for cat in categories
                ]
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500