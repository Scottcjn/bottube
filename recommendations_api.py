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
        word = word.strip()
        if len(word) > 2 and word not in stop_words:
            keywords.add(word)

    return keywords


def calculate_category_affinity(user_id):
    """Calculate user's category preferences based on watch history"""
    db = get_db()
    cursor = db.execute("""
        SELECT v.category, COUNT(*) as watch_count
        FROM view_history vh
        JOIN videos v ON vh.video_id = v.id
        WHERE vh.user_id = ? AND v.category IS NOT NULL
        GROUP BY v.category
        ORDER BY watch_count DESC
    """, (user_id,))

    categories = cursor.fetchall()
    total_watches = sum(cat['watch_count'] for cat in categories)

    if total_watches == 0:
        return {}

    # Convert to affinity scores (0-1)
    affinity = {}
    for cat in categories:
        affinity[cat['category']] = cat['watch_count'] / total_watches

    return affinity


@recommendations_api.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    """Get personalized video recommendations for the current user"""
    if not hasattr(g, 'user') or not g.user:
        return jsonify({'error': 'Authentication required'}), 401

    user_id = g.user['id']
    limit = request.args.get('limit', 10, type=int)
    algorithm = request.args.get('algorithm', 'content')

    if limit > 50:
        limit = 50

    try:
        if algorithm == 'collaborative':
            recommendations = get_collaborative_recommendations(user_id, limit)
        elif algorithm == 'trending':
            recommendations = get_trending_recommendations(limit)
        else:  # Default to content-based
            recommendations = engine.get_content_based_recommendations(user_id, limit)

        return jsonify({
            'recommendations': recommendations,
            'algorithm': algorithm,
            'user_id': user_id,
            'count': len(recommendations)
        })

    except Exception as e:
        return jsonify({'error': f'Failed to generate recommendations: {str(e)}'}), 500


def get_collaborative_recommendations(user_id, limit=10):
    """Get recommendations based on similar users' preferences"""
    db = get_db()

    # Find users with similar watch patterns
    similar_users_cursor = db.execute("""
        SELECT u2.user_id, COUNT(DISTINCT u2.video_id) as common_videos
        FROM (
            SELECT DISTINCT video_id
            FROM view_history
            WHERE user_id = ?
            LIMIT 50
        ) u1_videos
        JOIN view_history u2 ON u1_videos.video_id = u2.video_id
        WHERE u2.user_id != ?
        GROUP BY u2.user_id
        HAVING common_videos >= 2
        ORDER BY common_videos DESC
        LIMIT 10
    """, (user_id, user_id))

    similar_users = similar_users_cursor.fetchall()

    if not similar_users:
        return engine.get_popular_videos(limit)

    # Get videos watched by similar users but not by current user
    similar_user_ids = [str(user['user_id']) for user in similar_users]
    watched_by_user_cursor = db.execute("""
        SELECT DISTINCT video_id
        FROM view_history
        WHERE user_id = ?
    """, (user_id,))
    watched_by_user = [str(row['video_id']) for row in watched_by_user_cursor.fetchall()]

    if watched_by_user:
        watched_placeholders = ','.join('?' * len(watched_by_user))
        similar_user_placeholders = ','.join('?' * len(similar_user_ids))

        recommendations_cursor = db.execute(f"""
            SELECT v.id, v.title, v.views, v.likes, v.comments, v.upload_date,
                   COUNT(*) as recommendation_count
            FROM view_history vh
            JOIN videos v ON vh.video_id = v.id
            WHERE vh.user_id IN ({similar_user_placeholders})
              AND v.id NOT IN ({watched_placeholders})
            GROUP BY v.id, v.title, v.views, v.likes, v.comments, v.upload_date
            ORDER BY recommendation_count DESC, v.views DESC
            LIMIT ?
        """, similar_user_ids + watched_by_user + [limit])
    else:
        similar_user_placeholders = ','.join('?' * len(similar_user_ids))
        recommendations_cursor = db.execute(f"""
            SELECT v.id, v.title, v.views, v.likes, v.comments, v.upload_date,
                   COUNT(*) as recommendation_count
            FROM view_history vh
            JOIN videos v ON vh.video_id = v.id
            WHERE vh.user_id IN ({similar_user_placeholders})
            GROUP BY v.id, v.title, v.views, v.likes, v.comments, v.upload_date
            ORDER BY recommendation_count DESC, v.views DESC
            LIMIT ?
        """, similar_user_ids + [limit])

    videos = recommendations_cursor.fetchall()
    recommendations = []

    for video in videos:
        engagement = calculate_engagement_score(
            video['views'] or 0,
            video['likes'] or 0,
            video['comments'] or 0,
            video['upload_date']
        )

        recommendations.append({
            'video_id': video['id'],
            'title': video['title'],
            'similarity_score': video['recommendation_count'] / len(similar_users),
            'engagement_score': engagement,
            'combined_score': (video['recommendation_count'] / len(similar_users)) * 0.6 + engagement * 0.4
        })

    return recommendations


def get_trending_recommendations(limit=10):
    """Get trending videos based on recent engagement"""
    db = get_db()

    # Get videos with high recent engagement (last 7 days)
    cursor = db.execute("""
        SELECT v.id, v.title, v.views, v.likes, v.comments, v.upload_date,
               COUNT(vh.id) as recent_views
        FROM videos v
        LEFT JOIN view_history vh ON v.id = vh.video_id
            AND vh.watched_at > datetime('now', '-7 days')
        WHERE v.upload_date > datetime('now', '-30 days')
        GROUP BY v.id, v.title, v.views, v.likes, v.comments, v.upload_date
        ORDER BY recent_views DESC, v.views DESC
        LIMIT ?
    """, (limit,))

    videos = cursor.fetchall()
    recommendations = []

    for video in videos:
        engagement = calculate_engagement_score(
            video['views'] or 0,
            video['likes'] or 0,
            video['comments'] or 0,
            video['upload_date']
        )

        trending_score = (video['recent_views'] or 0) * 10 + engagement

        recommendations.append({
            'video_id': video['id'],
            'title': video['title'],
            'similarity_score': 0,
            'engagement_score': engagement,
            'combined_score': trending_score
        })

    return recommendations


@recommendations_api.route('/api/recommendations/feedback', methods=['POST'])
def recommendation_feedback():
    """Record user feedback on recommendations for future improvement"""
    if not hasattr(g, 'user') or not g.user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json()
    if not data or 'video_id' not in data or 'feedback' not in data:
        return jsonify({'error': 'Missing required fields: video_id, feedback'}), 400

    user_id = g.user['id']
    video_id = data['video_id']
    feedback = data['feedback']  # 'like', 'dislike', 'not_interested'

    if feedback not in ['like', 'dislike', 'not_interested']:
        return jsonify({'error': 'Invalid feedback value'}), 400

    try:
        db = get_db()
        # Store feedback in a recommendations_feedback table
        db.execute("""
            INSERT OR REPLACE INTO recommendations_feedback
            (user_id, video_id, feedback, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, video_id, feedback, datetime.now().isoformat()))
        db.commit()

        return jsonify({'message': 'Feedback recorded successfully'})

    except Exception as e:
        return jsonify({'error': f'Failed to record feedback: {str(e)}'}), 500


@recommendations_api.route('/api/recommendations/stats', methods=['GET'])
def recommendation_stats():
    """Get recommendation statistics for the current user"""
    if not hasattr(g, 'user') or not g.user:
        return jsonify({'error': 'Authentication required'}), 401

    user_id = g.user['id']

    try:
        db = get_db()

        # Get watch history count
        history_cursor = db.execute("""
            SELECT COUNT(DISTINCT video_id) as watched_count
            FROM view_history
            WHERE user_id = ?
        """, (user_id,))
        watched_count = history_cursor.fetchone()['watched_count']

        # Get category preferences
        category_affinity = calculate_category_affinity(user_id)

        # Get recent feedback stats
        feedback_cursor = db.execute("""
            SELECT feedback, COUNT(*) as count
            FROM recommendations_feedback
            WHERE user_id = ? AND created_at > datetime('now', '-30 days')
            GROUP BY feedback
        """, (user_id,))
        feedback_stats = {row['feedback']: row['count'] for row in feedback_cursor.fetchall()}

        return jsonify({
            'user_id': user_id,
            'watched_videos': watched_count,
            'category_preferences': category_affinity,
            'recent_feedback': feedback_stats,
            'recommendation_quality': {
                'data_points': watched_count,
                'personalization_level': 'high' if watched_count > 10 else 'medium' if watched_count > 5 else 'low'
            }
        })

    except Exception as e:
        return jsonify({'error': f'Failed to get stats: {str(e)}'}), 500