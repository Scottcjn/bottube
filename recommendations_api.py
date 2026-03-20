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

    keywords = {word for word in words if len(word) > 2 and word not in stop_words}
    return keywords


@recommendations_api.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    """Get personalized video recommendations for the current user"""
    try:
        # Check if user is logged in
        if not g.user:
            return jsonify({'error': 'Authentication required'}), 401

        user_id = g.user['id']
        limit = min(int(request.args.get('limit', 10)), 50)  # Max 50 recommendations

        # Get recommendations from engine
        recommendations = engine.get_recommendations_for_user(user_id, limit)

        if not recommendations:
            return jsonify({'recommendations': [], 'message': 'No recommendations available'})

        # Get full video details for recommended videos
        video_ids = [rec['video_id'] for rec in recommendations]
        placeholders = ','.join('?' * len(video_ids))

        db = get_db()
        cursor = db.execute(f"""
            SELECT v.id, v.title, v.description, v.thumbnail_url,
                   v.duration, v.views, v.likes, v.upload_date,
                   v.uploader_id, u.username as uploader_name
            FROM videos v
            JOIN users u ON v.uploader_id = u.id
            WHERE v.id IN ({placeholders})
            AND v.is_active = 1
        """, video_ids)

        videos = {row['id']: dict(row) for row in cursor.fetchall()}

        # Combine recommendation data with video details
        result = []
        for rec in recommendations:
            video_id = rec['video_id']
            if video_id in videos:
                video_data = videos[video_id]
                video_data.update({
                    'recommendation_score': rec['score'],
                    'recommendation_type': rec['type']
                })
                result.append(video_data)

        return jsonify({
            'recommendations': result,
            'count': len(result)
        })

    except Exception as e:
        return jsonify({'error': 'Failed to get recommendations', 'details': str(e)}), 500


@recommendations_api.route('/api/recommendations/trending', methods=['GET'])
def get_trending():
    """Get trending videos (public endpoint)"""
    try:
        limit = min(int(request.args.get('limit', 20)), 100)

        db = get_db()
        cursor = db.execute("""
            SELECT v.id, v.title, v.description, v.thumbnail_url,
                   v.duration, v.views, v.likes, v.upload_date,
                   v.uploader_id, u.username as uploader_name,
                   (COALESCE(v.views, 0) + COALESCE(v.likes, 0) * 2) as trending_score
            FROM videos v
            JOIN users u ON v.uploader_id = u.id
            WHERE v.is_active = 1
            AND v.upload_date >= datetime('now', '-7 days')
            ORDER BY trending_score DESC
            LIMIT ?
        """, (limit,))

        trending_videos = [dict(row) for row in cursor.fetchall()]

        return jsonify({
            'trending': trending_videos,
            'count': len(trending_videos)
        })

    except Exception as e:
        return jsonify({'error': 'Failed to get trending videos', 'details': str(e)}), 500


@recommendations_api.route('/api/recommendations/similar/<int:video_id>', methods=['GET'])
def get_similar_videos(video_id):
    """Get videos similar to a specific video"""
    try:
        limit = min(int(request.args.get('limit', 10)), 20)

        db = get_db()

        # Get the target video
        target_cursor = db.execute("""
            SELECT id, title, description, tags, category
            FROM videos
            WHERE id = ? AND is_active = 1
        """, (video_id,))
        target_video = target_cursor.fetchone()

        if not target_video:
            return jsonify({'error': 'Video not found'}), 404

        # Get candidate videos from same category or with similar tags
        candidates_cursor = db.execute("""
            SELECT id, title, description, tags, category
            FROM videos
            WHERE id != ? AND is_active = 1
            AND (category = ? OR tags LIKE '%' || ? || '%')
            ORDER BY upload_date DESC
            LIMIT 50
        """, (video_id, target_video['category'], target_video['tags'] or ''))
        candidate_videos = [dict(row) for row in candidates_cursor.fetchall()]

        if not candidate_videos:
            return jsonify({'similar': [], 'message': 'No similar videos found'})

        # Use TF-IDF to find similar videos
        all_videos = [dict(target_video)] + candidate_videos
        tfidf_vectors = engine.compute_tf_idf(all_videos)
        target_vector = tfidf_vectors.get(video_id, {})

        similarities = []
        for video in candidate_videos:
            candidate_vector = tfidf_vectors.get(video['id'], {})
            similarity = engine.cosine_similarity(target_vector, candidate_vector)
            similarities.append({
                'video_id': video['id'],
                'similarity': similarity
            })

        # Sort by similarity and get top results
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        top_similar = similarities[:limit]

        # Get full video details
        if top_similar:
            video_ids = [s['video_id'] for s in top_similar]
            placeholders = ','.join('?' * len(video_ids))

            details_cursor = db.execute(f"""
                SELECT v.id, v.title, v.description, v.thumbnail_url,
                       v.duration, v.views, v.likes, v.upload_date,
                       v.uploader_id, u.username as uploader_name
                FROM videos v
                JOIN users u ON v.uploader_id = u.id
                WHERE v.id IN ({placeholders})
            """, video_ids)

            video_details = {row['id']: dict(row) for row in details_cursor.fetchall()}

            result = []
            for sim in top_similar:
                video_id = sim['video_id']
                if video_id in video_details:
                    video_data = video_details[video_id]
                    video_data['similarity_score'] = sim['similarity']
                    result.append(video_data)

            return jsonify({
                'similar': result,
                'count': len(result)
            })
        else:
            return jsonify({'similar': [], 'message': 'No similar videos found'})

    except Exception as e:
        return jsonify({'error': 'Failed to get similar videos', 'details': str(e)}), 500
