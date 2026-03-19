from flask import Blueprint, request, jsonify, g
from database.models import Video, User, UserInteraction, db
from algorithms.recommendation_engine import RecommendationEngine
from algorithms.content_analyzer import ContentAnalyzer
from algorithms.trending_analyzer import TrendingAnalyzer
from utils.auth import require_auth
from utils.cache import cache
from datetime import datetime, timedelta
import numpy as np

recommendations_bp = Blueprint('recommendations', __name__)
rec_engine = RecommendationEngine()
content_analyzer = ContentAnalyzer()
trending_analyzer = TrendingAnalyzer()

@recommendations_bp.route('/personalized', methods=['GET'])
@require_auth
def get_personalized_recommendations():
    """Get personalized video recommendations for authenticated user"""
    try:
        user_id = g.current_user.id
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 50)
        
        # Check cache first
        cache_key = f"recommendations:user:{user_id}:page:{page}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return jsonify(cached_result)
        
        # Get user interaction history
        user_interactions = UserInteraction.query.filter_by(user_id=user_id).all()
        
        if not user_interactions:
            # New user - return trending videos
            return get_trending_videos()
        
        # Generate personalized recommendations
        recommendations = rec_engine.get_personalized_recommendations(
            user_id=user_id,
            limit=per_page,
            offset=(page - 1) * per_page
        )
        
        # Format response
        result = {
            'videos': [format_video_response(video) for video in recommendations],
            'page': page,
            'per_page': per_page,
            'total': len(recommendations),
            'recommendation_type': 'personalized'
        }
        
        # Cache for 15 minutes
        cache.set(cache_key, result, timeout=900)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': 'Failed to get recommendations', 'details': str(e)}), 500

@recommendations_bp.route('/trending', methods=['GET'])
def get_trending_videos():
    """Get trending videos based on engagement metrics"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 50)
        time_range = request.args.get('time_range', '24h')  # 24h, 7d, 30d
        category = request.args.get('category')
        
        cache_key = f"trending:{time_range}:{category}:{page}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return jsonify(cached_result)
        
        # Get trending videos
        trending_videos = trending_analyzer.get_trending_videos(
            time_range=time_range,
            category=category,
            limit=per_page,
            offset=(page - 1) * per_page
        )
        
        result = {
            'videos': [format_video_response(video) for video in trending_videos],
            'page': page,
            'per_page': per_page,
            'total': len(trending_videos),
            'time_range': time_range,
            'category': category,
            'recommendation_type': 'trending'
        }
        
        # Cache for 10 minutes
        cache.set(cache_key, result, timeout=600)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': 'Failed to get trending videos', 'details': str(e)}), 500

@recommendations_bp.route('/similar/<int:video_id>', methods=['GET'])
def get_similar_videos(video_id):
    """Get videos similar to the specified video"""
    try:
        limit = min(request.args.get('limit', 10, type=int), 20)
        
        cache_key = f"similar:{video_id}:{limit}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return jsonify(cached_result)
        
        # Get the target video
        target_video = Video.query.get(video_id)
        if not target_video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Find similar videos using content analysis
        similar_videos = content_analyzer.find_similar_videos(
            target_video_id=video_id,
            limit=limit
        )
        
        result = {
            'target_video': format_video_response(target_video),
            'similar_videos': [format_video_response(video) for video in similar_videos],
            'total': len(similar_videos),
            'recommendation_type': 'similar'
        }
        
        # Cache for 30 minutes
        cache.set(cache_key, result, timeout=1800)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': 'Failed to get similar videos', 'details': str(e)}), 500

@recommendations_bp.route('/category/<category>', methods=['GET'])
def get_category_recommendations(category):
    """Get recommended videos from a specific category"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 50)
        sort_by = request.args.get('sort_by', 'relevance')  # relevance, views, recent
        
        cache_key = f"category:{category}:{sort_by}:{page}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return jsonify(cached_result)
        
        user_id = getattr(g, 'current_user', {}).get('id') if hasattr(g, 'current_user') else None
        
        # Get category-based recommendations
        videos = rec_engine.get_category_recommendations(
            category=category,
            user_id=user_id,
            sort_by=sort_by,
            limit=per_page,
            offset=(page - 1) * per_page
        )
        
        result = {
            'videos': [format_video_response(video) for video in videos],
            'page': page,
            'per_page': per_page,
            'category': category,
            'sort_by': sort_by,
            'total': len(videos),
            'recommendation_type': 'category'
        }
        
        # Cache for 20 minutes
        cache.set(cache_key, result, timeout=1200)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': 'Failed to get category recommendations', 'details': str(e)}), 500

@recommendations_bp.route('/user-based/<int:user_id>', methods=['GET'])
def get_user_based_recommendations(user_id):
    """Get recommendations based on similar users' preferences"""
    try:
        limit = min(request.args.get('limit', 15, type=int), 30)
        
        cache_key = f"user_based:{user_id}:{limit}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return jsonify(cached_result)
        
        # Get user-based collaborative filtering recommendations
        recommendations = rec_engine.get_collaborative_recommendations(
            user_id=user_id,
            limit=limit
        )
        
        result = {
            'videos': [format_video_response(video) for video in recommendations],
            'total': len(recommendations),
            'recommendation_type': 'collaborative'
        }
        
        # Cache for 25 minutes
        cache.set(cache_key, result, timeout=1500)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': 'Failed to get user-based recommendations', 'details': str(e)}), 500

@recommendations_bp.route('/feed', methods=['GET'])
@require_auth
def get_recommendation_feed():
    """Get mixed recommendation feed combining multiple algorithms"""
    try:
        user_id = g.current_user.id
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 50)
        
        cache_key = f"feed:{user_id}:{page}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return jsonify(cached_result)
        
        # Generate mixed feed
        feed_videos = rec_engine.generate_mixed_feed(
            user_id=user_id,
            limit=per_page,
            offset=(page - 1) * per_page
        )
        
        result = {
            'videos': [format_video_response(video) for video in feed_videos],
            'page': page,
            'per_page': per_page,
            'total': len(feed_videos),
            'recommendation_type': 'mixed_feed'
        }
        
        # Cache for 10 minutes
        cache.set(cache_key, result, timeout=600)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': 'Failed to get recommendation feed', 'details': str(e)}), 500

@recommendations_bp.route('/refresh', methods=['POST'])
@require_auth
def refresh_recommendations():
    """Refresh user's recommendation cache"""
    try:
        user_id = g.current_user.id
        
        # Clear user's recommendation caches
        cache_patterns = [
            f"recommendations:user:{user_id}:*",
            f"feed:{user_id}:*"
        ]
        
        for pattern in cache_patterns:
            cache.delete_many(pattern)
        
        return jsonify({'message': 'Recommendations refreshed successfully'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to refresh recommendations', 'details': str(e)}), 500

@recommendations_bp.route('/feedback', methods=['POST'])
@require_auth
def submit_recommendation_feedback():
    """Submit feedback on recommendation quality"""
    try:
        user_id = g.current_user.id
        data = request.get_json()
        
        video_id = data.get('video_id')
        feedback_type = data.get('feedback_type')  # 'like', 'dislike', 'not_interested'
        recommendation_context = data.get('context', {})
        
        if not video_id or not feedback_type:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Record feedback for recommendation engine improvement
        rec_engine.record_feedback(
            user_id=user_id,
            video_id=video_id,
            feedback_type=feedback_type,
            context=recommendation_context
        )
        
        return jsonify({'message': 'Feedback recorded successfully'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to record feedback', 'details': str(e)}), 500

def format_video_response(video):
    """Format video object for API response"""
    return {
        'id': video.id,
        'title': video.title,
        'description': video.description[:200] + '...' if len(video.description) > 200 else video.description,
        'thumbnail_url': video.thumbnail_url,
        'duration': video.duration,
        'views': video.view_count,
        'likes': video.like_count,
        'category': video.category,
        'created_at': video.created_at.isoformat(),
        'uploader': {
            'id': video.uploader.id,
            'username': video.uploader.username,
            'profile_image': getattr(video.uploader, 'profile_image_url', None)
        },
        'engagement_score': getattr(video, 'engagement_score', 0),
        'recommendation_score': getattr(video, 'recommendation_score', 0)
    }