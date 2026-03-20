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


def get_similar_users(user_id, min_overlap=3):
    """Find users with similar viewing patterns"""
    db = get_db()

    # Get videos watched by current user
    cursor = db.execute("""
        SELECT video_id FROM view_history
        WHERE user_id = ?
    """, (user_id,))
    user_videos = {row['video_id'] for row in cursor.fetchall()}

    if len(user_videos) < min_overlap:
        return []

    # Find users who watched similar videos
    cursor = db.execute("""
        SELECT vh.user_id, COUNT(*) as overlap
        FROM view_history vh
        WHERE vh.video_id IN ({}) AND vh.user_id != ?
        GROUP BY vh.user_id
        HAVING COUNT(*) >= ?
        ORDER BY overlap DESC
        LIMIT 20
    """.format(','.join('?' * len(user_videos))),
                       list(user_videos) + [user_id, min_overlap])

    return cursor.fetchall()


def get_collaborative_recommendations(user_id, limit=20):
    """Get recommendations based on similar users"""
    similar_users = get_similar_users(user_id)
    if not similar_users:
        return []

    # Get videos watched by current user to exclude
    db = get_db()
    cursor = db.execute("""
        SELECT video_id FROM view_history WHERE user_id = ?
    """, (user_id,))
    watched_videos = {row['video_id'] for row in cursor.fetchall()}

    # Get videos watched by similar users
    similar_user_ids = [user['user_id'] for user in similar_users]
    placeholders = ','.join('?' * len(similar_user_ids))

    cursor = db.execute(f"""
        SELECT v.id, v.title, v.description, v.category, v.upload_date,
               v.views, v.likes, v.comments, COUNT(*) as recommendation_score
        FROM view_history vh
        JOIN videos v ON vh.video_id = v.id
        WHERE vh.user_id IN ({placeholders})
        AND vh.video_id NOT IN (SELECT video_id FROM view_history WHERE user_id = ?)
        GROUP BY v.id
        ORDER BY recommendation_score DESC, v.upload_date DESC
        LIMIT ?
    """, similar_user_ids + [user_id, limit])

    recommendations = []
    for row in cursor.fetchall():
        video = dict(row)
        video['reason'] = 'collaborative'
        recommendations.append(video)

    return recommendations


def get_content_based_recommendations(user_id, limit=20):
    """Get recommendations based on content similarity"""
    db = get_db()
    watch_history = get_user_watch_history(user_id, 20)

    if not watch_history:
        return []

    # Extract keywords from watched videos
    user_keywords = set()
    user_categories = Counter()

    for video in watch_history:
        # Extract keywords from title, description, tags
        text = f"{video['title']} {video['description'] or ''} {video.get('tags', '') or ''}"
        keywords = extract_keywords(text)
        user_keywords.update(keywords)

        if video['category']:
            user_categories[video['category']] += 1

    # Get candidate videos (not watched, recent)
    cursor = db.execute("""
        SELECT v.id, v.title, v.description, v.tags, v.category,
               v.upload_date, v.views, v.likes, v.comments
        FROM videos v
        WHERE v.id NOT IN (SELECT video_id FROM view_history WHERE user_id = ?)
        AND v.upload_date > date('now', '-30 days')
        ORDER BY v.upload_date DESC
        LIMIT 200
    """, (user_id,))

    candidates = cursor.fetchall()
    recommendations = []

    for video in candidates:
        score = 0

        # Content similarity score
        video_text = f"{video['title']} {video['description'] or ''} {video.get('tags', '') or ''}"
        video_keywords = extract_keywords(video_text)
        keyword_overlap = len(user_keywords.intersection(video_keywords))
        score += keyword_overlap * 2

        # Category preference
        if video['category'] in user_categories:
            score += user_categories[video['category']] * 3

        # Engagement boost
        if video['views'] > 0:
            engagement = (video['likes'] + video['comments']) / video['views']
            score += engagement * 10

        if score > 0:
            video_dict = dict(video)
            video_dict['recommendation_score'] = score
            video_dict['reason'] = 'content'
            recommendations.append(video_dict)

    # Sort by score and return top recommendations
    recommendations.sort(key=lambda x: x['recommendation_score'], reverse=True)
    return recommendations[:limit]


def get_trending_videos(limit=20, time_window_days=7):
    """Get trending videos based on recent engagement"""
    db = get_db()
    cursor = db.execute("""
        SELECT v.id, v.title, v.description, v.category, v.upload_date,
               v.views, v.likes, v.comments,
               COUNT(vh.id) as recent_views
        FROM videos v
        LEFT JOIN view_history vh ON v.id = vh.video_id
            AND vh.watched_at > date('now', '-{} days')
        WHERE v.upload_date > date('now', '-30 days')
        GROUP BY v.id
        HAVING v.views > 0
        ORDER BY recent_views DESC, (v.likes + v.comments) / v.views DESC
        LIMIT ?
    """.format(time_window_days), (limit,))

    trending = []
    for row in cursor.fetchall():
        video = dict(row)
        video['reason'] = 'trending'
        trending.append(video)

    return trending


@recommendations_api.route('/api/recommendations')
def get_recommendations():
    """Main recommendation endpoint"""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400

    limit = min(int(request.args.get('limit', 20)), 50)
    rec_type = request.args.get('type', 'mixed')

    try:
        if rec_type == 'collaborative':
            recommendations = get_collaborative_recommendations(user_id, limit)
        elif rec_type == 'content':
            recommendations = get_content_based_recommendations(user_id, limit)
        elif rec_type == 'trending':
            recommendations = get_trending_videos(limit)
        else:  # mixed
            # Combine different recommendation types
            collab_recs = get_collaborative_recommendations(user_id, limit // 2)
            content_recs = get_content_based_recommendations(user_id, limit // 2)
            trending_recs = get_trending_videos(limit // 4)

            # Merge and deduplicate
            seen_videos = set()
            recommendations = []

            for rec_list in [collab_recs, content_recs, trending_recs]:
                for video in rec_list:
                    if video['id'] not in seen_videos:
                        recommendations.append(video)
                        seen_videos.add(video['id'])

            # Sort by recommendation score if available, otherwise by upload date
            recommendations.sort(
                key=lambda x: (x.get('recommendation_score', 0), x['upload_date']),
                reverse=True
            )
            recommendations = recommendations[:limit]

        return jsonify({
            'recommendations': recommendations,
            'count': len(recommendations),
            'type': rec_type
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/recommendations/feedback', methods=['POST'])
def record_feedback():
    """Record user feedback on recommendations"""
    data = request.get_json()
    user_id = data.get('user_id')
    video_id = data.get('video_id')
    feedback_type = data.get('feedback_type')  # 'like', 'dislike', 'not_interested'

    if not all([user_id, video_id, feedback_type]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        db = get_db()
        db.execute("""
            INSERT OR REPLACE INTO recommendations_feedback
            (user_id, video_id, feedback_type, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, video_id, feedback_type, datetime.now().isoformat()))
        db.commit()

        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/recommendations/stats')
def get_recommendation_stats():
    """Get recommendation system statistics"""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400

    try:
        db = get_db()

        # Get user's watch history count
        cursor = db.execute("""
            SELECT COUNT(*) as watch_count
            FROM view_history
            WHERE user_id = ?
        """, (user_id,))
        watch_count = cursor.fetchone()['watch_count']

        # Get feedback count
        cursor = db.execute("""
            SELECT feedback_type, COUNT(*) as count
            FROM recommendations_feedback
            WHERE user_id = ?
            GROUP BY feedback_type
        """, (user_id,))
        feedback_stats = {row['feedback_type']: row['count'] for row in cursor.fetchall()}

        # Get similar users count
        similar_users = get_similar_users(user_id)

        return jsonify({
            'watch_history_count': watch_count,
            'similar_users_count': len(similar_users),
            'feedback_stats': feedback_stats
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
