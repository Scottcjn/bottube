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
    stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'a', 'an'}
    
    keywords = set()
    for word in words:
        if len(word) > 3 and word not in stop_words:
            keywords.add(word)
    
    return keywords

def content_similarity_score(video1, video2):
    """Calculate content similarity between two videos"""
    keywords1 = extract_keywords(f"{video1['title']} {video1.get('description', '')} {video1.get('tags', '')}")
    keywords2 = extract_keywords(f"{video2['title']} {video2.get('description', '')} {video2.get('tags', '')}")
    
    if not keywords1 or not keywords2:
        return 0.0
    
    intersection = len(keywords1 & keywords2)
    union = len(keywords1 | keywords2)
    
    return intersection / union if union > 0 else 0.0

@recommendations_api.route('/api/recommendations/feed', methods=['GET'])
def get_recommendation_feed():
    """Get personalized feed for logged-in user"""
    if not g.user:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        user_id = g.user['id']
        limit = request.args.get('limit', 20, type=int)
        
        # Get personalized recommendations
        recommendations = engine.get_recommendations(user_id, limit)
        
        return jsonify({
            'success': True,
            'recommendations': recommendations,
            'user_id': user_id
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to generate recommendations: {str(e)}'}), 500

@recommendations_api.route('/api/recommendations/trending', methods=['GET'])
def get_trending_feed():
    """Get trending videos feed"""
    try:
        limit = request.args.get('limit', 20, type=int)
        days = request.args.get('days', 7, type=int)
        
        trending_videos = engine.get_trending_videos(limit, days)
        
        return jsonify({
            'success': True,
            'trending': trending_videos
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to get trending videos: {str(e)}'}), 500

@recommendations_api.route('/api/recommendations/similar/<int:video_id>', methods=['GET'])
def get_similar_videos(video_id):
    """Get videos similar to the specified video"""
    try:
        limit = request.args.get('limit', 10, type=int)
        
        similar_videos = engine.get_similar_videos(video_id, limit)
        
        return jsonify({
            'success': True,
            'similar_videos': similar_videos,
            'video_id': video_id
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to get similar videos: {str(e)}'}), 500

@recommendations_api.route('/api/recommendations/user-profile/<int:user_id>', methods=['GET'])
def get_user_profile(user_id):
    """Get user's preference profile (for debugging/analytics)"""
    if not g.user or g.user['id'] != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        user_prefs = engine.get_user_preferences(user_id)
        
        return jsonify({
            'success': True,
            'preferences': user_prefs,
            'user_id': user_id
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to get user profile: {str(e)}'}), 500

@recommendations_api.route('/api/recommendations/stats', methods=['GET'])
def get_recommendation_stats():
    """Get overall recommendation system statistics"""
    try:
        db = get_db()
        
        # Get total videos, users, and views
        cursor = db.execute("SELECT COUNT(*) as total_videos FROM videos")
        total_videos = cursor.fetchone()['total_videos']
        
        cursor = db.execute("SELECT COUNT(*) as total_users FROM users")
        total_users = cursor.fetchone()['total_users']
        
        cursor = db.execute("SELECT COUNT(*) as total_views FROM view_history")
        total_views = cursor.fetchone()['total_views']
        
        # Get active users in last 7 days
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        cursor = db.execute("""
            SELECT COUNT(DISTINCT user_id) as active_users 
            FROM view_history 
            WHERE watched_at >= ?
        """, (week_ago,))
        active_users = cursor.fetchone()['active_users']
        
        return jsonify({
            'success': True,
            'stats': {
                'total_videos': total_videos,
                'total_users': total_users,
                'total_views': total_views,
                'active_users_7d': active_users
            }
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to get stats: {str(e)}'}), 500