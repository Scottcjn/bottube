from flask import Blueprint, request, jsonify
from functools import wraps
import jwt
from datetime import datetime, timedelta
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging
from database import get_db
import os

recommendations_bp = Blueprint('recommendations', __name__)
logger = logging.getLogger(__name__)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, os.getenv('JWT_SECRET_KEY', 'secret'), algorithms=['HS256'])
            current_user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token is invalid'}), 401
        
        return f(current_user_id, *args, **kwargs)
    return decorated

@recommendations_bp.route('/personalized', methods=['GET'])
@token_required
def get_personalized_recommendations(current_user_id):
    """Get personalized video recommendations for a user"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get user's watch history and preferences
        cursor.execute("""
            SELECT v.id, v.title, v.description, v.tags, v.category, 
                   v.views, v.upload_date, u.username as channel_name,
                   COALESCE(vh.watch_duration, 0) as watch_duration,
                   COALESCE(vh.completed, 0) as completed
            FROM videos v
            JOIN users u ON v.user_id = u.id
            LEFT JOIN view_history vh ON v.id = vh.video_id AND vh.user_id = ?
            WHERE v.id IN (
                SELECT video_id FROM view_history WHERE user_id = ?
            )
            ORDER BY vh.timestamp DESC
            LIMIT 50
        """, (current_user_id, current_user_id))
        
        watch_history = cursor.fetchall()
        
        if not watch_history:
            # If no history, return trending videos
            return get_trending_videos()
        
        # Get user's liked categories and tags
        cursor.execute("""
            SELECT v.category, v.tags, COUNT(*) as frequency
            FROM videos v
            JOIN view_history vh ON v.id = vh.video_id
            WHERE vh.user_id = ? AND vh.completed = 1
            GROUP BY v.category, v.tags
            ORDER BY frequency DESC
        """, (current_user_id,))
        
        preferences = cursor.fetchall()
        
        # Get all available videos (excluding already watched)
        cursor.execute("""
            SELECT v.id, v.title, v.description, v.tags, v.category,
                   v.views, v.upload_date, u.username as channel_name,
                   v.duration, v.thumbnail_url
            FROM videos v
            JOIN users u ON v.user_id = u.id
            WHERE v.id NOT IN (
                SELECT video_id FROM view_history WHERE user_id = ?
            )
            AND v.status = 'active'
            ORDER BY v.upload_date DESC
            LIMIT 1000
        """, (current_user_id,))
        
        available_videos = cursor.fetchall()
        
        # Calculate recommendation scores
        recommendations = calculate_recommendation_scores(
            watch_history, preferences, available_videos, current_user_id
        )
        
        # Format response
        result = []
        for video in recommendations[:20]:  # Top 20 recommendations
            result.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'thumbnail_url': video['thumbnail_url'],
                'duration': video['duration'],
                'views': video['views'],
                'upload_date': video['upload_date'].isoformat() if video['upload_date'] else None,
                'channel_name': video['channel_name'],
                'category': video['category'],
                'tags': video['tags'].split(',') if video['tags'] else [],
                'recommendation_score': video['score']
            })
        
        return jsonify({
            'success': True,
            'recommendations': result,
            'total': len(result)
        })
        
    except Exception as e:
        logger.error(f"Error getting personalized recommendations: {str(e)}")
        return jsonify({'error': 'Failed to get recommendations'}), 500

@recommendations_bp.route('/trending', methods=['GET'])
def get_trending_videos():
    """Get trending videos based on views, engagement, and recency"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        category = request.args.get('category')
        
        offset = (page - 1) * limit
        
        # Calculate trending score based on views, likes, comments, and recency
        base_query = """
            SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
                   v.views, v.upload_date, v.category, v.tags,
                   u.username as channel_name,
                   COALESCE(like_count, 0) as likes,
                   COALESCE(comment_count, 0) as comments,
                   (
                       (v.views * 0.4) + 
                       (COALESCE(like_count, 0) * 0.3) + 
                       (COALESCE(comment_count, 0) * 0.2) +
                       (CASE 
                           WHEN v.upload_date > datetime('now', '-1 day') THEN 100
                           WHEN v.upload_date > datetime('now', '-7 days') THEN 50
                           WHEN v.upload_date > datetime('now', '-30 days') THEN 20
                           ELSE 5
                       END * 0.1)
                   ) as trending_score
            FROM videos v
            JOIN users u ON v.user_id = u.id
            LEFT JOIN (
                SELECT video_id, COUNT(*) as like_count
                FROM likes
                GROUP BY video_id
            ) l ON v.id = l.video_id
            LEFT JOIN (
                SELECT video_id, COUNT(*) as comment_count
                FROM comments
                GROUP BY video_id
            ) c ON v.id = c.video_id
            WHERE v.status = 'active'
        """
        
        params = []
        if category:
            base_query += " AND v.category = ?"
            params.append(category)
        
        base_query += " ORDER BY trending_score DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(base_query, params)
        videos = cursor.fetchall()
        
        # Get total count
        count_query = "SELECT COUNT(*) FROM videos v WHERE v.status = 'active'"
        count_params = []
        if category:
            count_query += " AND v.category = ?"
            count_params.append(category)
        
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()[0]
        
        # Format response
        result = []
        for video in videos:
            result.append({
                'id': video[0],
                'title': video[1],
                'description': video[2],
                'thumbnail_url': video[3],
                'duration': video[4],
                'views': video[5],
                'upload_date': video[6].isoformat() if video[6] else None,
                'category': video[7],
                'tags': video[8].split(',') if video[8] else [],
                'channel_name': video[9],
                'likes': video[10],
                'comments': video[11],
                'trending_score': round(video[12], 2)
            })
        
        return jsonify({
            'success': True,
            'videos': result,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting trending videos: {str(e)}")
        return jsonify({'error': 'Failed to get trending videos'}), 500

@recommendations_bp.route('/similar/<int:video_id>', methods=['GET'])
def get_similar_videos(video_id):
    """Get videos similar to a specific video"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get the target video
        cursor.execute("""
            SELECT id, title, description, tags, category, user_id
            FROM videos
            WHERE id = ? AND status = 'active'
        """, (video_id,))
        
        target_video = cursor.fetchone()
        if not target_video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Get all other videos for comparison
        cursor.execute("""
            SELECT v.id, v.title, v.description, v.tags, v.category,
                   v.views, v.upload_date, v.duration, v.thumbnail_url,
                   u.username as channel_name, v.user_id
            FROM videos v
            JOIN users u ON v.user_id = u.id
            WHERE v.id != ? AND v.status = 'active'
            LIMIT 500
        """, (video_id,))
        
        candidate_videos = cursor.fetchall()
        
        # Calculate similarity scores
        similar_videos = calculate_video_similarity(target_video, candidate_videos)
        
        # Format response
        result = []
        for video in similar_videos[:10]:  # Top 10 similar videos
            result.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'thumbnail_url': video['thumbnail_url'],
                'duration': video['duration'],
                'views': video['views'],
                'upload_date': video['upload_date'].isoformat() if video['upload_date'] else None,
                'channel_name': video['channel_name'],
                'category': video['category'],
                'tags': video['tags'].split(',') if video['tags'] else [],
                'similarity_score': video['similarity_score']
            })
        
        return jsonify({
            'success': True,
            'similar_videos': result,
            'target_video_id': video_id
        })
        
    except Exception as e:
        logger.error(f"Error getting similar videos: {str(e)}")
        return jsonify({'error': 'Failed to get similar videos'}), 500

@recommendations_bp.route('/categories', methods=['GET'])
def get_categories():
    """Get available video categories"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute("""
            SELECT category, COUNT(*) as video_count
            FROM videos
            WHERE status = 'active' AND category IS NOT NULL
            GROUP BY category
            ORDER BY video_count DESC
        """)
        
        categories = cursor.fetchall()
        
        result = []
        for category in categories:
            result.append({
                'name': category[0],
                'video_count': category[1]
            })
        
        return jsonify({
            'success': True,
            'categories': result
        })
        
    except Exception as e:
        logger.error(f"Error getting categories: {str(e)}")
        return jsonify({'error': 'Failed to get categories'}), 500

def calculate_recommendation_scores(watch_history, preferences, available_videos, user_id):
    """Calculate recommendation scores for videos"""
    scored_videos = []
    
    # Extract preferred categories and tags
    preferred_categories = set()
    preferred_tags = set()
    
    for pref in preferences:
        if pref[0]:  # category
            preferred_categories.add(pref[0])
        if pref[1]:  # tags
            for tag in pref[1].split(','):
                preferred_tags.add(tag.strip())
    
    # Calculate scores for each video
    for video in available_videos:
        score = 0
        
        # Category preference (30%)
        if video[4] in preferred_categories:
            score += 30
        
        # Tag preference (25%)
        if video[3]:
            video_tags = set(tag.strip() for tag in video[3].split(','))
            tag_overlap = len(video_tags.intersection(preferred_tags))
            if tag_overlap > 0:
                score += min(25, tag_overlap * 5)
        
        # Popularity factor (20%)
        if video[5]:  # views
            score += min(20, video[5] / 1000)
        
        # Recency factor (15%)
        if video[6]:  # upload_date
            days_ago = (datetime.now() - video[6]).days
            if days_ago <= 1:
                score += 15
            elif days_ago <= 7:
                score += 10
            elif days_ago <= 30:
                score += 5
        
        # Content similarity (10%)
        # Use TF-IDF on title and description
        if video[1] and video[2]:  # title and description
            content_score = calculate_content_similarity(watch_history, video)
            score += content_score * 10
        
        scored_videos.append({
            'id': video[0],
            'title': video[1],
            'description': video[2],
            'tags': video[3],
            'category': video[4],
            'views': video[5],
            'upload_date': video[6],
            'channel_name': video[7],
            'duration': video[8],
            'thumbnail_url': video[9],
            'score': round(score, 2)
        })
    
    # Sort by score
    scored_videos.sort(key=lambda x: x['score'], reverse=True)
    return scored_videos

def calculate_content_similarity(watch_history, target_video):
    """Calculate content similarity using TF-IDF"""
    if not watch_history:
        return 0
    
    # Prepare documents
    documents = []
    
    # Add watched video content
    for video in watch_history:
        content = f"{video[1]} {video[2]}"  # title + description
        documents.append(content)
    
    # Add target video content
    target_content = f"{target_video[1]} {target_video[2]}"
    documents.append(target_content)
    
    if len(documents) < 2:
        return 0
    
    try:
        # Calculate TF-IDF
        vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
        tfidf_matrix = vectorizer.fit_transform(documents)
        
        # Calculate similarity between target and watched videos
        target_vector = tfidf_matrix[-1]
        similarities = cosine_similarity(target_vector, tfidf_matrix[:-1])
        
        # Return average similarity
        return np.mean(similarities)
    except:
        return 0

def calculate_video_similarity(target_video, candidate_videos):
    """Calculate similarity between target video and candidates"""
    similar_videos = []
    
    target_content = f"{target_video[1]} {target_video[2]}"
    target_tags = set(target_video[3].split(',')) if target_video[3] else set()
    target_category = target_video[4]
    target_channel = target_video[5]
    
    for video in candidate_videos:
        similarity_score = 0
        
        # Category similarity (40%)
        if video[4] == target_category:
            similarity_score += 40
        
        # Tag similarity (30%)
        if video[3]:
            video_tags = set(video[3].split(','))
            tag_overlap = len(target_tags.intersection(video_tags))
            if len(target_tags) > 0:
                similarity_score += (tag_overlap / len(target_tags)) * 30
        
        # Same channel bonus (20%)
        if video[10] == target_channel:
            similarity_score += 20
        
        # Content similarity (10%)
        video_content = f"{video[1]} {video[2]}"
        try:
            vectorizer = TfidfVectorizer(stop_words='english')
            tfidf_matrix = vectorizer.fit_transform([target_content, video_content])
            content_similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            similarity_score += content_similarity * 10
        except:
            pass
        
        if similarity_score > 0:
            similar_videos.append({
                'id': video[0],
                'title': video[1],
                'description': video[2],
                'tags': video[3],
                'category': video[4],
                'views': video[5],
                'upload_date': video[6],
                'duration': video[7],
                'thumbnail_url': video[8],
                'channel_name': video[9],
                'similarity_score': round(similarity_score, 2)
            })
    
    # Sort by similarity score
    similar_videos.sort(key=lambda x: x['similarity_score'], reverse=True)
    return similar_videos