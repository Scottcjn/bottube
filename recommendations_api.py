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
        SELECT user_id, COUNT(*) as overlap_count
        FROM view_history
        WHERE video_id IN ({}) AND user_id != ?
        GROUP BY user_id
        HAVING overlap_count >= ?
        ORDER BY overlap_count DESC
        LIMIT 20
    """.format(','.join('?' * len(user_videos))), list(user_videos) + [user_id, min_overlap])

    return cursor.fetchall()


def get_collaborative_recommendations(user_id, limit=10):
    """Get recommendations based on similar users' viewing patterns"""
    similar_users = get_similar_users(user_id)

    if not similar_users:
        return []

    db = get_db()
    similar_user_ids = [row['user_id'] for row in similar_users]

    # Get videos watched by current user to exclude them
    cursor = db.execute("""
        SELECT video_id FROM view_history WHERE user_id = ?
    """, (user_id,))
    watched_videos = {row['video_id'] for row in cursor.fetchall()}

    # Get videos watched by similar users that current user hasn't seen
    placeholders = ','.join('?' * len(similar_user_ids))
    cursor = db.execute(f"""
        SELECT v.id, v.title, v.description, v.tags, v.category,
               v.upload_date, COUNT(*) as recommendation_score
        FROM view_history vh
        JOIN videos v ON vh.video_id = v.id
        WHERE vh.user_id IN ({placeholders})
        AND v.id NOT IN ({','.join('?' * len(watched_videos)) if watched_videos else '0'})
        GROUP BY v.id
        ORDER BY recommendation_score DESC, v.upload_date DESC
        LIMIT ?
    """, similar_user_ids + (list(watched_videos) if watched_videos else []) + [limit])

    return cursor.fetchall()


def get_content_based_recommendations(user_id, limit=10):
    """Get recommendations based on content similarity to user's watch history"""
    watch_history = get_user_watch_history(user_id, limit=20)

    if not watch_history:
        return []

    # Extract interests from watch history
    user_interests = defaultdict(int)
    user_categories = defaultdict(int)

    for video in watch_history:
        # Extract keywords from title and description
        keywords = extract_keywords(f"{video['title']} {video['description'] or ''}")
        for keyword in keywords:
            user_interests[keyword] += 1

        # Track category preferences
        if video['category']:
            user_categories[video['category']] += 1

    # Get candidate videos (not already watched)
    db = get_db()
    cursor = db.execute("""
        SELECT video_id FROM view_history WHERE user_id = ?
    """, (user_id,))
    watched_videos = {row['video_id'] for row in cursor.fetchall()}

    cursor = db.execute("""
        SELECT id, title, description, tags, category, upload_date
        FROM videos
        WHERE id NOT IN ({})
        ORDER BY upload_date DESC
        LIMIT 500
    """.format(','.join('?' * len(watched_videos)) if watched_videos else '0'),
                       list(watched_videos) if watched_videos else [])

    candidates = cursor.fetchall()

    # Score candidates based on content similarity
    scored_videos = []
    for video in candidates:
        score = 0

        # Content similarity score
        video_keywords = extract_keywords(f"{video['title']} {video['description'] or ''}")
        for keyword in video_keywords:
            if keyword in user_interests:
                score += user_interests[keyword]

        # Category preference bonus
        if video['category'] and video['category'] in user_categories:
            score += user_categories[video['category']] * 2

        if score > 0:
            scored_videos.append((video, score))

    # Sort by score and return top recommendations
    scored_videos.sort(key=lambda x: x[1], reverse=True)
    return [video for video, score in scored_videos[:limit]]


def get_trending_videos(limit=20, time_window_hours=24):
    """Get trending videos based on recent view activity"""
    db = get_db()
    cutoff_time = datetime.now() - timedelta(hours=time_window_hours)

    cursor = db.execute("""
        SELECT v.id, v.title, v.description, v.tags, v.category,
               v.upload_date, COUNT(vh.id) as view_count,
               COUNT(DISTINCT vh.user_id) as unique_viewers
        FROM videos v
        LEFT JOIN view_history vh ON v.id = vh.video_id
            AND vh.watched_at >= ?
        GROUP BY v.id
        HAVING view_count > 0
        ORDER BY view_count DESC, unique_viewers DESC
        LIMIT ?
    """, (cutoff_time.isoformat(), limit))

    return cursor.fetchall()


@recommendations_api.route('/api/recommendations')
def get_recommendations():
    """Get personalized video recommendations for a user"""
    user_id = request.args.get('user_id', type=int)
    limit = request.args.get('limit', 10, type=int)
    rec_type = request.args.get('type', 'mixed')  # 'collaborative', 'content', 'trending', 'mixed'

    if not user_id:
        return jsonify({'error': 'user_id required'}), 400

    recommendations = []

    try:
        if rec_type == 'collaborative':
            recommendations = get_collaborative_recommendations(user_id, limit)
        elif rec_type == 'content':
            recommendations = get_content_based_recommendations(user_id, limit)
        elif rec_type == 'trending':
            recommendations = get_trending_videos(limit)
        else:  # mixed
            # Get a mix of different recommendation types
            collab_recs = get_collaborative_recommendations(user_id, limit//2)
            content_recs = get_content_based_recommendations(user_id, limit//2)
            trending_recs = get_trending_videos(limit//3)

            # Combine and deduplicate
            seen_ids = set()
            recommendations = []

            for rec_list in [collab_recs, content_recs, trending_recs]:
                for rec in rec_list:
                    if rec['id'] not in seen_ids:
                        recommendations.append(rec)
                        seen_ids.add(rec['id'])
                        if len(recommendations) >= limit:
                            break
                if len(recommendations) >= limit:
                    break

        # Convert to JSON-serializable format
        result = []
        for rec in recommendations:
            result.append({
                'id': rec['id'],
                'title': rec['title'],
                'description': rec['description'],
                'category': rec['category'],
                'upload_date': rec['upload_date'],
                'tags': rec.get('tags'),
                'recommendation_score': rec.get('recommendation_score', 0),
                'view_count': rec.get('view_count', 0),
                'unique_viewers': rec.get('unique_viewers', 0)
            })

        return jsonify({
            'recommendations': result,
            'type': rec_type,
            'user_id': user_id
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/trending')
def get_trending():
    """Get trending videos"""
    limit = request.args.get('limit', 20, type=int)
    time_window = request.args.get('time_window', 24, type=int)  # hours

    try:
        trending = get_trending_videos(limit, time_window)

        result = []
        for video in trending:
            result.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'category': video['category'],
                'upload_date': video['upload_date'],
                'view_count': video['view_count'],
                'unique_viewers': video['unique_viewers']
            })

        return jsonify({
            'trending': result,
            'time_window_hours': time_window
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/feedback', methods=['POST'])
def record_feedback():
    """Record user feedback on recommendations"""
    data = request.get_json()

    if not data or 'user_id' not in data or 'video_id' not in data or 'feedback_type' not in data:
        return jsonify({'error': 'user_id, video_id, and feedback_type required'}), 400

    user_id = data['user_id']
    video_id = data['video_id']
    feedback_type = data['feedback_type']

    if feedback_type not in ['like', 'dislike', 'not_interested']:
        return jsonify({'error': 'feedback_type must be like, dislike, or not_interested'}), 400

    try:
        db = get_db()
        db.execute("""
            INSERT OR REPLACE INTO recommendations_feedback
            (user_id, video_id, feedback_type, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, video_id, feedback_type, datetime.now().isoformat()))
        db.commit()

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/watch_history', methods=['POST'])
def record_watch():
    """Record a video view in watch history"""
    data = request.get_json()

    if not data or 'user_id' not in data or 'video_id' not in data:
        return jsonify({'error': 'user_id and video_id required'}), 400

    user_id = data['user_id']
    video_id = data['video_id']
    watch_duration = data.get('watch_duration', 0)

    try:
        db = get_db()
        db.execute("""
            INSERT OR IGNORE INTO view_history
            (user_id, video_id, watched_at, watch_duration)
            VALUES (?, ?, ?, ?)
        """, (user_id, video_id, datetime.now().isoformat(), watch_duration))
        db.commit()

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
