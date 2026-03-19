from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import random
import json
import os

app = Flask(__name__)

# Mock database for demonstration
MOCK_VIDEOS = [
    {
        "id": 1,
        "title": "Introduction to Machine Learning",
        "description": "Learn the basics of ML with practical examples",
        "category": "education",
        "tags": ["ml", "ai", "education"],
        "views": 15420,
        "likes": 892,
        "duration": 1200,
        "upload_date": "2024-01-15",
        "creator": "TechEdu",
        "thumbnail": "https://example.com/thumb1.jpg"
    },
    {
        "id": 2,
        "title": "Python Web Development Tutorial",
        "description": "Build web applications with Python and Flask",
        "category": "programming",
        "tags": ["python", "flask", "web"],
        "views": 23450,
        "likes": 1234,
        "duration": 2400,
        "upload_date": "2024-01-20",
        "creator": "CodeMaster",
        "thumbnail": "https://example.com/thumb2.jpg"
    },
    {
        "id": 3,
        "title": "Cooking Italian Pasta",
        "description": "Traditional Italian pasta recipes from scratch",
        "category": "cooking",
        "tags": ["cooking", "italian", "pasta"],
        "views": 45678,
        "likes": 2345,
        "duration": 900,
        "upload_date": "2024-01-25",
        "creator": "ChefAntonio",
        "thumbnail": "https://example.com/thumb3.jpg"
    },
    {
        "id": 4,
        "title": "Deep Learning with PyTorch",
        "description": "Advanced neural networks using PyTorch framework",
        "category": "education",
        "tags": ["deep-learning", "pytorch", "ai"],
        "views": 8934,
        "likes": 567,
        "duration": 3600,
        "upload_date": "2024-02-01",
        "creator": "AIResearcher",
        "thumbnail": "https://example.com/thumb4.jpg"
    },
    {
        "id": 5,
        "title": "JavaScript ES6 Features",
        "description": "Modern JavaScript features and best practices",
        "category": "programming",
        "tags": ["javascript", "es6", "frontend"],
        "views": 19876,
        "likes": 987,
        "duration": 1800,
        "upload_date": "2024-02-05",
        "creator": "JSGuru",
        "thumbnail": "https://example.com/thumb5.jpg"
    }
]

MOCK_USER_PREFERENCES = {
    "1": {
        "categories": ["education", "programming"],
        "tags": ["ml", "ai", "python"],
        "viewed_videos": [1, 2],
        "liked_videos": [1],
        "watch_time_preference": "long"
    },
    "2": {
        "categories": ["cooking", "lifestyle"],
        "tags": ["cooking", "italian"],
        "viewed_videos": [3],
        "liked_videos": [3],
        "watch_time_preference": "medium"
    }
}

def calculate_trending_score(video):
    """Calculate trending score based on views, likes, and recency"""
    upload_date = datetime.strptime(video['upload_date'], '%Y-%m-%d')
    days_old = (datetime.now() - upload_date).days
    
    # Weight recent videos higher
    recency_factor = max(0.1, 1 - (days_old / 30))
    
    # Combine views and likes with recency
    engagement_score = (video['views'] + video['likes'] * 10) * recency_factor
    
    return engagement_score

def calculate_similarity(video1, video2):
    """Calculate similarity between two videos based on tags and category"""
    score = 0
    
    # Category match
    if video1['category'] == video2['category']:
        score += 0.3
    
    # Tag overlap
    tags1 = set(video1['tags'])
    tags2 = set(video2['tags'])
    tag_overlap = len(tags1.intersection(tags2)) / len(tags1.union(tags2))
    score += tag_overlap * 0.7
    
    return score

def get_user_preferences(user_id):
    """Get user preferences or return default"""
    return MOCK_USER_PREFERENCES.get(user_id, {
        "categories": [],
        "tags": [],
        "viewed_videos": [],
        "liked_videos": [],
        "watch_time_preference": "medium"
    })

def calculate_personalized_score(video, user_prefs):
    """Calculate personalized recommendation score"""
    score = 0
    
    # Category preference
    if video['category'] in user_prefs.get('categories', []):
        score += 0.4
    
    # Tag preference
    user_tags = set(user_prefs.get('tags', []))
    video_tags = set(video['tags'])
    tag_match = len(user_tags.intersection(video_tags)) / max(len(user_tags), 1)
    score += tag_match * 0.3
    
    # Duration preference
    duration_pref = user_prefs.get('watch_time_preference', 'medium')
    video_duration = video['duration']
    
    if duration_pref == 'short' and video_duration < 600:
        score += 0.2
    elif duration_pref == 'medium' and 600 <= video_duration <= 1800:
        score += 0.2
    elif duration_pref == 'long' and video_duration > 1800:
        score += 0.2
    
    # Popularity boost
    popularity_score = min(1.0, video['views'] / 50000)
    score += popularity_score * 0.1
    
    return score

@app.route('/api/recommendations/personalized', methods=['GET'])
def get_personalized_recommendations():
    """Get personalized video recommendations for a user"""
    try:
        user_id = request.args.get('user_id')
        limit = int(request.args.get('limit', 10))
        
        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400
        
        user_prefs = get_user_preferences(user_id)
        viewed_videos = set(user_prefs.get('viewed_videos', []))
        
        # Filter out already viewed videos
        candidate_videos = [v for v in MOCK_VIDEOS if v['id'] not in viewed_videos]
        
        # Calculate personalized scores
        scored_videos = []
        for video in candidate_videos:
            score = calculate_personalized_score(video, user_prefs)
            scored_videos.append({**video, 'recommendation_score': score})
        
        # Sort by score and limit results
        recommendations = sorted(scored_videos, key=lambda x: x['recommendation_score'], reverse=True)[:limit]
        
        return jsonify({
            'status': 'success',
            'recommendations': recommendations,
            'user_id': user_id,
            'count': len(recommendations)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommendations/trending', methods=['GET'])
def get_trending_videos():
    """Get trending videos based on views, likes, and recency"""
    try:
        limit = int(request.args.get('limit', 10))
        category = request.args.get('category')
        
        videos = MOCK_VIDEOS.copy()
        
        # Filter by category if specified
        if category:
            videos = [v for v in videos if v['category'] == category]
        
        # Calculate trending scores
        scored_videos = []
        for video in videos:
            score = calculate_trending_score(video)
            scored_videos.append({**video, 'trending_score': score})
        
        # Sort by trending score and limit results
        trending = sorted(scored_videos, key=lambda x: x['trending_score'], reverse=True)[:limit]
        
        return jsonify({
            'status': 'success',
            'trending': trending,
            'category': category,
            'count': len(trending)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommendations/similar', methods=['GET'])
def get_similar_videos():
    """Get videos similar to a specific video"""
    try:
        video_id = request.args.get('video_id', type=int)
        limit = int(request.args.get('limit', 5))
        
        if not video_id:
            return jsonify({'error': 'Video ID is required'}), 400
        
        # Find the reference video
        reference_video = next((v for v in MOCK_VIDEOS if v['id'] == video_id), None)
        if not reference_video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Calculate similarity scores for other videos
        candidate_videos = [v for v in MOCK_VIDEOS if v['id'] != video_id]
        similar_videos = []
        
        for video in candidate_videos:
            similarity = calculate_similarity(reference_video, video)
            similar_videos.append({**video, 'similarity_score': similarity})
        
        # Sort by similarity and limit results
        recommendations = sorted(similar_videos, key=lambda x: x['similarity_score'], reverse=True)[:limit]
        
        return jsonify({
            'status': 'success',
            'reference_video': reference_video,
            'similar_videos': recommendations,
            'count': len(recommendations)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommendations/categories', methods=['GET'])
def get_categories():
    """Get available video categories"""
    try:
        categories = list(set(video['category'] for video in MOCK_VIDEOS))
        
        return jsonify({
            'status': 'success',
            'categories': categories
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommendations/user-feedback', methods=['POST'])
def submit_user_feedback():
    """Submit user feedback for recommendation improvement"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'JSON data is required'}), 400
        
        user_id = data.get('user_id')
        video_id = data.get('video_id')
        feedback_type = data.get('feedback_type')  # 'like', 'dislike', 'watch', 'skip'
        
        if not all([user_id, video_id, feedback_type]):
            return jsonify({'error': 'user_id, video_id, and feedback_type are required'}), 400
        
        # In a real implementation, this would update the user's preference model
        # For now, we'll just acknowledge the feedback
        
        return jsonify({
            'status': 'success',
            'message': 'Feedback recorded successfully',
            'user_id': user_id,
            'video_id': video_id,
            'feedback_type': feedback_type
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommendations/stats', methods=['GET'])
def get_recommendation_stats():
    """Get recommendation engine statistics"""
    try:
        total_videos = len(MOCK_VIDEOS)
        categories = list(set(video['category'] for video in MOCK_VIDEOS))
        total_views = sum(video['views'] for video in MOCK_VIDEOS)
        total_likes = sum(video['likes'] for video in MOCK_VIDEOS)
        
        # Calculate average metrics
        avg_views = total_views / total_videos if total_videos > 0 else 0
        avg_likes = total_likes / total_videos if total_videos > 0 else 0
        
        return jsonify({
            'status': 'success',
            'stats': {
                'total_videos': total_videos,
                'total_categories': len(categories),
                'categories': categories,
                'total_views': total_views,
                'total_likes': total_likes,
                'average_views': round(avg_views, 2),
                'average_likes': round(avg_likes, 2)
            }
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)