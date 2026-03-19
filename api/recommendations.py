from flask import Flask, request, jsonify
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random

app = Flask(__name__)

# Mock data for demonstration
mock_videos = [
    {"id": 1, "title": "Introduction to Python", "category": "programming", "duration": 600, "views": 15000, "likes": 1200},
    {"id": 2, "title": "Machine Learning Basics", "category": "ai", "duration": 900, "views": 22000, "likes": 1800},
    {"id": 3, "title": "Web Development Tutorial", "category": "programming", "duration": 1200, "views": 18000, "likes": 1500},
    {"id": 4, "title": "Data Science Fundamentals", "category": "data", "duration": 800, "views": 12000, "likes": 950},
    {"id": 5, "title": "React.js Complete Guide", "category": "programming", "duration": 1800, "views": 35000, "likes": 2800},
    {"id": 6, "title": "Deep Learning with PyTorch", "category": "ai", "duration": 2100, "views": 28000, "likes": 2200},
    {"id": 7, "title": "Database Design Principles", "category": "data", "duration": 1000, "views": 14000, "likes": 1100},
    {"id": 8, "title": "JavaScript ES6 Features", "category": "programming", "duration": 700, "views": 19000, "likes": 1600},
    {"id": 9, "title": "Computer Vision Basics", "category": "ai", "duration": 1500, "views": 21000, "likes": 1700},
    {"id": 10, "title": "SQL Query Optimization", "category": "data", "duration": 900, "views": 16000, "likes": 1300}
]

mock_user_history = {
    1: [1, 2, 5],
    2: [3, 4, 7],
    3: [2, 6, 9],
    4: [1, 3, 8],
    5: [4, 6, 7]
}

def calculate_similarity_score(video1, video2):
    """Calculate similarity between two videos based on category and engagement"""
    category_match = 1.0 if video1["category"] == video2["category"] else 0.3
    
    # Normalize engagement metrics
    max_views = max([v["views"] for v in mock_videos])
    max_likes = max([v["likes"] for v in mock_videos])
    
    v1_engagement = (video1["views"] / max_views + video1["likes"] / max_likes) / 2
    v2_engagement = (video2["views"] / max_views + video2["likes"] / max_likes) / 2
    
    engagement_similarity = 1 - abs(v1_engagement - v2_engagement)
    
    return category_match * 0.7 + engagement_similarity * 0.3

def get_user_preferences(user_id):
    """Extract user preferences based on viewing history"""
    if user_id not in mock_user_history:
        return {}
    
    watched_videos = [v for v in mock_videos if v["id"] in mock_user_history[user_id]]
    
    if not watched_videos:
        return {}
    
    categories = {}
    total_duration = 0
    total_engagement = 0
    
    for video in watched_videos:
        categories[video["category"]] = categories.get(video["category"], 0) + 1
        total_duration += video["duration"]
        total_engagement += video["views"] + video["likes"]
    
    preferred_category = max(categories, key=categories.get)
    avg_duration = total_duration / len(watched_videos)
    
    return {
        "preferred_category": preferred_category,
        "avg_duration": avg_duration,
        "category_distribution": categories,
        "engagement_threshold": total_engagement / len(watched_videos)
    }

@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    user_id = request.args.get('user_id', type=int)
    limit = request.args.get('limit', 10, type=int)
    
    if not user_id:
        return jsonify({"error": "user_id parameter is required"}), 400
    
    preferences = get_user_preferences(user_id)
    
    if not preferences:
        # New user - return trending videos
        trending_videos = sorted(mock_videos, key=lambda x: x["views"] + x["likes"], reverse=True)[:limit]
        return jsonify({
            "user_id": user_id,
            "recommendations": trending_videos,
            "algorithm": "trending_fallback"
        })
    
    # Score videos based on user preferences
    scored_videos = []
    watched_ids = mock_user_history.get(user_id, [])
    
    for video in mock_videos:
        if video["id"] in watched_ids:
            continue
            
        score = 0
        
        # Category preference
        if video["category"] == preferences["preferred_category"]:
            score += 0.4
        elif video["category"] in preferences["category_distribution"]:
            score += 0.2
        
        # Duration preference
        duration_diff = abs(video["duration"] - preferences["avg_duration"])
        duration_score = max(0, 1 - duration_diff / preferences["avg_duration"])
        score += duration_score * 0.3
        
        # Engagement score
        engagement = video["views"] + video["likes"]
        if engagement >= preferences["engagement_threshold"]:
            score += 0.3
        
        scored_videos.append({**video, "score": score})
    
    # Sort by score and return top recommendations
    recommendations = sorted(scored_videos, key=lambda x: x["score"], reverse=True)[:limit]
    
    return jsonify({
        "user_id": user_id,
        "recommendations": recommendations,
        "algorithm": "collaborative_content_hybrid"
    })

@app.route('/api/trending', methods=['GET'])
def get_trending():
    limit = request.args.get('limit', 10, type=int)
    category = request.args.get('category', type=str)
    timeframe = request.args.get('timeframe', '24h', type=str)
    
    # Filter by category if specified
    videos = mock_videos
    if category:
        videos = [v for v in videos if v["category"].lower() == category.lower()]
    
    # Apply timeframe weighting (mock implementation)
    timeframe_weights = {
        '1h': 1.5,
        '24h': 1.2,
        '7d': 1.0,
        '30d': 0.8
    }
    
    weight = timeframe_weights.get(timeframe, 1.0)
    
    # Calculate trending score
    trending_videos = []
    for video in videos:
        # Mock trending calculation: views + likes * weight + random factor for recent activity
        trending_score = (video["views"] + video["likes"] * 2) * weight + random.randint(0, 1000)
        trending_videos.append({**video, "trending_score": trending_score})
    
    # Sort by trending score
    trending_videos = sorted(trending_videos, key=lambda x: x["trending_score"], reverse=True)[:limit]
    
    return jsonify({
        "trending": trending_videos,
        "timeframe": timeframe,
        "category": category,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/similar', methods=['GET'])
def get_similar():
    video_id = request.args.get('video_id', type=int)
    limit = request.args.get('limit', 5, type=int)
    
    if not video_id:
        return jsonify({"error": "video_id parameter is required"}), 400
    
    # Find the target video
    target_video = next((v for v in mock_videos if v["id"] == video_id), None)
    
    if not target_video:
        return jsonify({"error": "Video not found"}), 404
    
    # Calculate similarity scores
    similar_videos = []
    for video in mock_videos:
        if video["id"] == video_id:
            continue
            
        similarity_score = calculate_similarity_score(target_video, video)
        similar_videos.append({**video, "similarity_score": similarity_score})
    
    # Sort by similarity and return top results
    similar_videos = sorted(similar_videos, key=lambda x: x["similarity_score"], reverse=True)[:limit]
    
    return jsonify({
        "video_id": video_id,
        "target_video": target_video,
        "similar_videos": similar_videos,
        "algorithm": "content_based_similarity"
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)