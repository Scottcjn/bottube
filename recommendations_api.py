import json
import sqlite3
import math
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from flask import Blueprint, request, jsonify, g
from bottube_server import get_db

recommendations_api = Blueprint('recommendations_api', __name__)

def calculate_engagement_score(views, likes, comments, upload_date):
    """Calculate engagement score with time decay"""
    if views == 0:
        return 0
    
    engagement_rate = (likes + comments * 2) / views
    
    # Time decay factor (newer content gets boost)
    days_old = (datetime.now() - datetime.fromisoformat(upload_date)).days
    time_factor = math.exp(-days_old / 7.0)  # 7-day half-life
    
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
    # Extract keywords from titles and descriptions
    v1_keywords = extract_keywords(video1['title'] + ' ' + (video1['description'] or ''))
    v2_keywords = extract_keywords(video2['title'] + ' ' + (video2['description'] or ''))
    
    # Add tags if available
    if video1['tags']:
        v1_keywords.update(tag.strip().lower() for tag in video1['tags'].split(','))
    if video2['tags']:
        v2_keywords.update(tag.strip().lower() for tag in video2['tags'].split(','))
    
    if not v1_keywords or not v2_keywords:
        return 0
    
    # Calculate Jaccard similarity
    intersection = len(v1_keywords.intersection(v2_keywords))
    union = len(v1_keywords.union(v2_keywords))
    
    similarity = intersection / union if union > 0 else 0
    
    # Boost if same category
    if video1.get('category') == video2.get('category') and video1.get('category'):
        similarity *= 1.3
    
    return similarity

def get_collaborative_recommendations(user_id, limit=10):
    """Get recommendations based on collaborative filtering"""
    db = get_db()
    
    # Find users with similar viewing patterns
    cursor = db.execute("""
        SELECT vh2.user_id, COUNT(*) as common_videos
        FROM view_history vh1
        JOIN view_history vh2 ON vh1.video_id = vh2.video_id
        WHERE vh1.user_id = ? AND vh2.user_id != ?
        GROUP BY vh2.user_id
        HAVING common_videos >= 3
        ORDER BY common_videos DESC
        LIMIT 20
    """, (user_id, user_id))
    
    similar_users = cursor.fetchall()
    
    if not similar_users:
        return []
    
    similar_user_ids = [str(u['user_id']) for u in similar_users]
    placeholders = ','.join(['?' for _ in similar_user_ids])
    
    # Get videos watched by similar users but not by current user
    query = f"""
        SELECT v.id, v.title, v.description, v.channel_id, v.views, v.likes, 
               v.upload_date, COUNT(*) as recommendation_strength
        FROM view_history vh
        JOIN videos v ON vh.video_id = v.id
        WHERE vh.user_id IN ({placeholders})
        AND v.id NOT IN (
            SELECT video_id FROM view_history WHERE user_id = ?
        )
        GROUP BY v.id
        ORDER BY recommendation_strength DESC, v.views DESC
        LIMIT ?
    """
    
    cursor = db.execute(query, similar_user_ids + [user_id, limit])
    return cursor.fetchall()

def get_content_based_recommendations(user_id, limit=10):
    """Get recommendations based on content similarity"""
    watch_history = get_user_watch_history(user_id, 20)
    
    if not watch_history:
        return []
    
    db = get_db()
    
    # Get all videos not watched by user
    cursor = db.execute("""
        SELECT v.id, v.title, v.description, v.tags, v.category, v.channel_id,
               v.views, v.likes, v.upload_date
        FROM videos v
        WHERE v.id NOT IN (
            SELECT video_id FROM view_history WHERE user_id = ?
        )
        ORDER BY v.upload_date DESC
        LIMIT 100
    """, (user_id,))
    
    candidate_videos = cursor.fetchall()
    
    # Calculate similarity scores
    recommendations = []
    for candidate in candidate_videos:
        total_similarity = 0
        for watched_video in watch_history:
            similarity = content_similarity_score(
                dict(watched_video), 
                dict(candidate)
            )
            total_similarity += similarity
        
        avg_similarity = total_similarity / len(watch_history)
        
        if avg_similarity > 0.1:  # Minimum similarity threshold
            recommendations.append({
                'video': dict(candidate),
                'similarity_score': avg_similarity
            })
    
    # Sort by similarity score
    recommendations.sort(key=lambda x: x['similarity_score'], reverse=True)
    
    return [rec['video'] for rec in recommendations[:limit]]

@recommendations_api.route('/api/recommendations')
def get_personalized_recommendations():
    user_id = request.args.get('user_id')
    limit = int(request.args.get('limit', 20))
    
    if not user_id:
        return jsonify({'error': 'user_id parameter required'}), 400
    
    try:
        # Get both collaborative and content-based recommendations
        collaborative_recs = get_collaborative_recommendations(user_id, limit // 2)
        content_recs = get_content_based_recommendations(user_id, limit // 2)
        
        # Combine and format recommendations
        all_recommendations = []
        seen_video_ids = set()
        
        # Add collaborative recommendations
        for video in collaborative_recs:
            if video['id'] not in seen_video_ids:
                all_recommendations.append({
                    'id': video['id'],
                    'title': video['title'],
                    'description': video['description'],
                    'channel_id': video['channel_id'],
                    'views': video['views'],
                    'likes': video['likes'],
                    'upload_date': video['upload_date'],
                    'recommendation_type': 'collaborative'
                })
                seen_video_ids.add(video['id'])
        
        # Add content-based recommendations
        for video in content_recs:
            if video['id'] not in seen_video_ids:
                all_recommendations.append({
                    'id': video['id'],
                    'title': video['title'],
                    'description': video['description'],
                    'channel_id': video['channel_id'],
                    'views': video['views'],
                    'likes': video['likes'],
                    'upload_date': video['upload_date'],
                    'recommendation_type': 'content_based'
                })
                seen_video_ids.add(video['id'])
        
        return jsonify({
            'recommendations': all_recommendations[:limit],
            'total': len(all_recommendations)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@recommendations_api.route('/api/trending')
def get_trending_videos():
    limit = int(request.args.get('limit', 20))
    time_window = request.args.get('time_window', '7d')  # 1d, 7d, 30d
    
    # Convert time window to days
    days_map = {'1d': 1, '7d': 7, '30d': 30}
    days = days_map.get(time_window, 7)
    
    try:
        db = get_db()
        
        # Get videos with engagement metrics
        cursor = db.execute("""
            SELECT v.id, v.title, v.description, v.channel_id, v.views, v.likes,
                   v.upload_date, COUNT(c.id) as comment_count
            FROM videos v
            LEFT JOIN comments c ON v.id = c.video_id
            WHERE datetime(v.upload_date) >= datetime('now', '-{} days')
            GROUP BY v.id
            HAVING v.views > 0
        """.format(days))
        
        videos = cursor.fetchall()
        
        # Calculate engagement scores
        trending_videos = []
        for video in videos:
            engagement_score = calculate_engagement_score(
                video['views'], 
                video['likes'] or 0,
                video['comment_count'] or 0,
                video['upload_date']
            )
            
            trending_videos.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'channel_id': video['channel_id'],
                'views': video['views'],
                'likes': video['likes'],
                'upload_date': video['upload_date'],
                'comment_count': video['comment_count'],
                'engagement_score': round(engagement_score, 2)
            })
        
        # Sort by engagement score
        trending_videos.sort(key=lambda x: x['engagement_score'], reverse=True)
        
        return jsonify({
            'trending': trending_videos[:limit],
            'time_window': time_window,
            'total': len(trending_videos)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@recommendations_api.route('/api/similar')
def get_similar_videos():
    video_id = request.args.get('video_id')
    limit = int(request.args.get('limit', 10))
    
    if not video_id:
        return jsonify({'error': 'video_id parameter required'}), 400
    
    try:
        db = get_db()
        
        # Get the reference video
        cursor = db.execute("""
            SELECT id, title, description, tags, category, channel_id
            FROM videos WHERE id = ?
        """, (video_id,))
        
        ref_video = cursor.fetchone()
        if not ref_video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Get candidate videos (excluding the reference video)
        cursor = db.execute("""
            SELECT id, title, description, tags, category, channel_id, views, 
                   likes, upload_date
            FROM videos 
            WHERE id != ?
            ORDER BY upload_date DESC
            LIMIT 100
        """, (video_id,))
        
        candidate_videos = cursor.fetchall()
        
        # Calculate similarity scores
        similar_videos = []
        ref_video_dict = dict(ref_video)
        
        for candidate in candidate_videos:
            candidate_dict = dict(candidate)
            similarity = content_similarity_score(ref_video_dict, candidate_dict)
            
            if similarity > 0.15:  # Minimum similarity threshold
                similar_videos.append({
                    'id': candidate['id'],
                    'title': candidate['title'],
                    'description': candidate['description'],
                    'channel_id': candidate['channel_id'],
                    'views': candidate['views'],
                    'likes': candidate['likes'],
                    'upload_date': candidate['upload_date'],
                    'similarity_score': round(similarity, 3)
                })
        
        # Sort by similarity score
        similar_videos.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return jsonify({
            'similar_videos': similar_videos[:limit],
            'reference_video_id': video_id,
            'total': len(similar_videos)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500