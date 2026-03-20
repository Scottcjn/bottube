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
        # Clean word and check if it's meaningful
        clean_word = ''.join(c for c in word if c.isalnum())
        if len(clean_word) > 2 and clean_word not in stop_words:
            keywords.add(clean_word)

    return keywords


@recommendations_api.route('/api/recommendations/personalized', methods=['GET'])
def get_personalized_recommendations():
    """Get personalized recommendations for the current user"""
    if 'user_id' not in g or not g.user_id:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        limit = min(int(request.args.get('limit', 20)), 50)
        recommendations = engine.recommend_videos(g.user_id, limit)

        # Format response
        formatted_recs = []
        for video in recommendations:
            formatted_recs.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'thumbnail': video.get('thumbnail'),
                'duration': video.get('duration'),
                'views': video.get('views', 0),
                'likes': video.get('likes', 0),
                'upload_date': video['upload_date'],
                'uploader': video.get('uploader_name'),
                'category': video.get('category'),
                'score': round(video.get('recommendation_score', 0), 2)
            })

        return jsonify({
            'recommendations': formatted_recs,
            'total': len(formatted_recs)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/recommendations/trending', methods=['GET'])
def get_trending_recommendations():
    """Get trending videos"""
    try:
        limit = min(int(request.args.get('limit', 20)), 50)
        trending = engine.get_trending_videos(limit)

        formatted_trending = []
        for video in trending:
            formatted_trending.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'thumbnail': video.get('thumbnail'),
                'duration': video.get('duration'),
                'views': video.get('views', 0),
                'likes': video.get('likes', 0),
                'upload_date': video['upload_date'],
                'uploader': video.get('uploader_name'),
                'category': video.get('category'),
                'recent_views': video.get('recent_views', 0)
            })

        return jsonify({
            'trending': formatted_trending,
            'total': len(formatted_trending)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/recommendations/similar/<int:video_id>', methods=['GET'])
def get_similar_recommendations(video_id):
    """Get videos similar to a specific video"""
    try:
        limit = min(int(request.args.get('limit', 10)), 20)
        similar = engine.get_similar_videos(video_id, limit)

        formatted_similar = []
        for video in similar:
            formatted_similar.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'thumbnail': video.get('thumbnail'),
                'duration': video.get('duration'),
                'views': video.get('views', 0),
                'likes': video.get('likes', 0),
                'upload_date': video['upload_date'],
                'uploader': video.get('uploader_name'),
                'category': video.get('category'),
                'similarity_score': round(video.get('similarity_score', 0), 2)
            })

        return jsonify({
            'similar_videos': formatted_similar,
            'total': len(formatted_similar),
            'base_video_id': video_id
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/recommendations/categories', methods=['GET'])
def get_category_recommendations():
    """Get recommendations by category"""
    try:
        category = request.args.get('category')
        if not category:
            return jsonify({'error': 'Category parameter required'}), 400

        limit = min(int(request.args.get('limit', 20)), 50)
        db = get_db()

        cursor = db.execute("""
            SELECT v.*, u.username as uploader_name
            FROM videos v
            JOIN users u ON v.uploader_id = u.id
            WHERE v.category = ?
            ORDER BY v.upload_date DESC
            LIMIT ?
        """, (category, limit))

        videos = cursor.fetchall()
        formatted_videos = []

        for video in videos:
            formatted_videos.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'thumbnail': video.get('thumbnail'),
                'duration': video.get('duration'),
                'views': video.get('views', 0),
                'likes': video.get('likes', 0),
                'upload_date': video['upload_date'],
                'uploader': video.get('uploader_name'),
                'category': video.get('category')
            })

        return jsonify({
            'category_videos': formatted_videos,
            'category': category,
            'total': len(formatted_videos)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/recommendations/user-stats', methods=['GET'])
def get_user_recommendation_stats():
    """Get user's recommendation statistics and preferences"""
    if 'user_id' not in g or not g.user_id:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        preferences = engine.get_user_preferences(g.user_id)
        watch_history = get_user_watch_history(g.user_id, 10)

        # Format watch history
        formatted_history = []
        for video in watch_history:
            formatted_history.append({
                'id': video['id'],
                'title': video['title'],
                'category': video['category'],
                'watched_at': video['watched_at']
            })

        return jsonify({
            'preferences': preferences,
            'recent_watches': formatted_history,
            'total_preferences': len(preferences)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
