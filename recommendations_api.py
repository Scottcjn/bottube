# SPDX-License-Identifier: MIT
import json
import sqlite3
import math
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from flask import Blueprint, request, jsonify, g
from bottube_server import get_db

recommendations_api = Blueprint('recommendations_api', __name__)


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

    # Find other users and their overlap
    cursor = db.execute("""
        SELECT vh.user_id, vh.video_id
        FROM view_history vh
        WHERE vh.user_id != ?
    """, (user_id,))

    user_overlap = defaultdict(set)
    for row in cursor.fetchall():
        other_user_id = row['user_id']
        video_id = row['video_id']
        if video_id in user_videos:
            user_overlap[other_user_id].add(video_id)

    # Filter users with sufficient overlap and calculate similarity
    similar_users = []
    for other_user_id, overlap_videos in user_overlap.items():
        if len(overlap_videos) >= min_overlap:
            # Get total videos watched by other user
            cursor = db.execute("""
                SELECT COUNT(DISTINCT video_id) as total
                FROM view_history
                WHERE user_id = ?
            """, (other_user_id,))
            other_total = cursor.fetchone()['total']

            # Calculate Jaccard similarity
            union_size = len(user_videos) + other_total - len(overlap_videos)
            similarity = len(overlap_videos) / max(union_size, 1)

            similar_users.append({
                'user_id': other_user_id,
                'similarity': similarity,
                'overlap_count': len(overlap_videos)
            })

    return sorted(similar_users, key=lambda x: x['similarity'], reverse=True)[:10]


def get_content_based_recommendations(user_id, limit=20):
    """Get recommendations based on content similarity to user's watch history"""
    db = get_db()

    # Get user's watch history
    watch_history = get_user_watch_history(user_id, limit=100)
    if not watch_history:
        return []

    # Extract user's content preferences
    user_keywords = Counter()
    user_categories = Counter()
    watched_video_ids = set()

    for video in watch_history:
        watched_video_ids.add(video['id'])

        # Extract keywords from title, description, tags
        text = f"{video['title'] or ''} {video['description'] or ''} {video['tags'] or ''}"
        keywords = extract_keywords(text)
        for keyword in keywords:
            user_keywords[keyword] += 1

        if video['category']:
            user_categories[video['category']] += 1

    # Get candidate videos (not watched by user)
    cursor = db.execute("""
        SELECT id, title, description, tags, category, upload_date,
               view_count, like_count
        FROM videos
        WHERE id NOT IN ({}) AND status = 'public'
        ORDER BY upload_date DESC
        LIMIT 200
    """.format(','.join('?' * len(watched_video_ids))), list(watched_video_ids))

    candidate_videos = cursor.fetchall()
    scored_videos = []

    for video in candidate_videos:
        score = 0

        # Content similarity score
        text = f"{video['title'] or ''} {video['description'] or ''} {video['tags'] or ''}"
        video_keywords = extract_keywords(text)

        # Keyword overlap score
        common_keywords = video_keywords.intersection(set(user_keywords.keys()))
        if common_keywords:
            keyword_score = sum(user_keywords[keyword] for keyword in common_keywords)
            score += keyword_score * 0.7

        # Category preference score
        if video['category'] and video['category'] in user_categories:
            score += user_categories[video['category']] * 0.3

        # Engagement boost
        if video['view_count'] and video['view_count'] > 0:
            score += math.log(video['view_count']) * 0.1

        if video['like_count'] and video['like_count'] > 0:
            score += math.log(video['like_count']) * 0.05

        if score > 0:
            scored_videos.append({
                'video': dict(video),
                'score': score,
                'reason': 'content_similarity'
            })

    return sorted(scored_videos, key=lambda x: x['score'], reverse=True)[:limit]


def get_collaborative_recommendations(user_id, limit=20):
    """Get recommendations based on similar users' preferences"""
    similar_users = get_similar_users(user_id)
    if not similar_users:
        return []

    db = get_db()

    # Get videos watched by current user
    cursor = db.execute("""
        SELECT video_id FROM view_history WHERE user_id = ?
    """, (user_id,))
    watched_videos = {row['video_id'] for row in cursor.fetchall()}

    # Get videos liked by similar users
    video_scores = defaultdict(float)
    video_info = {}

    for similar_user in similar_users:
        similar_user_id = similar_user['user_id']
        similarity_weight = similar_user['similarity']

        # Get videos watched by similar user that current user hasn't watched
        cursor = db.execute("""
            SELECT v.id, v.title, v.description, v.category, v.upload_date,
                   v.view_count, v.like_count
            FROM view_history vh
            JOIN videos v ON vh.video_id = v.id
            WHERE vh.user_id = ? AND v.id NOT IN ({})
            AND v.status = 'public'
        """.format(','.join('?' * len(watched_videos))),
                  [similar_user_id] + list(watched_videos))

        for video in cursor.fetchall():
            video_id = video['id']
            video_scores[video_id] += similarity_weight
            if video_id not in video_info:
                video_info[video_id] = dict(video)

    # Convert to list and sort
    recommendations = []
    for video_id, score in video_scores.items():
        if video_id in video_info:
            recommendations.append({
                'video': video_info[video_id],
                'score': score,
                'reason': 'collaborative_filtering'
            })

    return sorted(recommendations, key=lambda x: x['score'], reverse=True)[:limit]


def get_trending_videos(timeframe='24h', limit=20):
    """Get trending videos based on recent engagement"""
    db = get_db()

    # Calculate time threshold
    if timeframe == '1h':
        hours = 1
    elif timeframe == '24h':
        hours = 24
    elif timeframe == '7d':
        hours = 168
    else:
        hours = 24

    time_threshold = datetime.now() - timedelta(hours=hours)

    cursor = db.execute("""
        SELECT v.id, v.title, v.description, v.category, v.upload_date,
               v.view_count, v.like_count,
               COUNT(vh.id) as recent_views
        FROM videos v
        LEFT JOIN view_history vh ON v.id = vh.video_id
            AND vh.watched_at > ?
        WHERE v.status = 'public'
        GROUP BY v.id
        HAVING recent_views > 0 OR v.upload_date > ?
        ORDER BY recent_views DESC, v.like_count DESC
        LIMIT ?
    """, (time_threshold, time_threshold, limit))

    trending_videos = []
    for video in cursor.fetchall():
        trending_videos.append({
            'video': dict(video),
            'score': video['recent_views'],
            'reason': 'trending'
        })

    return trending_videos


# API Endpoints
@recommendations_api.route('/api/recommendations/<int:user_id>')
def get_recommendations(user_id):
    """Get personalized recommendations for a user"""
    try:
        # Get different types of recommendations
        content_recs = get_content_based_recommendations(user_id, limit=10)
        collab_recs = get_collaborative_recommendations(user_id, limit=10)
        trending_recs = get_trending_videos(limit=5)

        # Combine and diversify recommendations
        all_recommendations = content_recs + collab_recs + trending_recs

        # Remove duplicates while preserving order
        seen_videos = set()
        unique_recommendations = []
        for rec in all_recommendations:
            video_id = rec['video']['id']
            if video_id not in seen_videos:
                seen_videos.add(video_id)
                unique_recommendations.append(rec)

        return jsonify({
            'recommendations': unique_recommendations[:20],
            'total': len(unique_recommendations)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/trending')
def api_trending():
    """Get trending videos"""
    try:
        timeframe = request.args.get('timeframe', '24h')
        limit = int(request.args.get('limit', 20))

        trending_videos = get_trending_videos(timeframe, limit)

        return jsonify({
            'trending': trending_videos,
            'timeframe': timeframe,
            'total': len(trending_videos)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/similar-videos/<int:video_id>')
def get_similar_videos(video_id):
    """Get videos similar to a specific video"""
    try:
        db = get_db()

        # Get the target video
        cursor = db.execute("""
            SELECT id, title, description, tags, category
            FROM videos WHERE id = ? AND status = 'public'
        """, (video_id,))
        target_video = cursor.fetchone()

        if not target_video:
            return jsonify({'error': 'Video not found'}), 404

        # Extract keywords from target video
        text = f"{target_video['title'] or ''} {target_video['description'] or ''} {target_video['tags'] or ''}"
        target_keywords = extract_keywords(text)
        target_category = target_video['category']

        # Get candidate videos
        cursor = db.execute("""
            SELECT id, title, description, tags, category, upload_date,
                   view_count, like_count
            FROM videos
            WHERE id != ? AND status = 'public'
            ORDER BY upload_date DESC
            LIMIT 100
        """, (video_id,))

        candidate_videos = cursor.fetchall()
        similar_videos = []

        for video in candidate_videos:
            score = 0

            # Content similarity
            text = f"{video['title'] or ''} {video['description'] or ''} {video['tags'] or ''}"
            video_keywords = extract_keywords(text)

            # Keyword overlap
            common_keywords = target_keywords.intersection(video_keywords)
            if common_keywords:
                score += len(common_keywords) * 2

            # Category match
            if video['category'] == target_category:
                score += 5

            # Engagement boost
            if video['view_count'] and video['view_count'] > 0:
                score += math.log(video['view_count']) * 0.1

            if score > 0:
                similar_videos.append({
                    'video': dict(video),
                    'score': score,
                    'reason': 'content_similarity'
                })

        # Sort and limit results
        similar_videos.sort(key=lambda x: x['score'], reverse=True)
        limit = int(request.args.get('limit', 10))

        return jsonify({
            'similar_videos': similar_videos[:limit],
            'target_video_id': video_id,
            'total': len(similar_videos)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Submit user feedback on recommendations"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        video_id = data.get('video_id')
        feedback_type = data.get('feedback_type')  # 'like', 'dislike', 'not_interested'

        if not all([user_id, video_id, feedback_type]):
            return jsonify({'error': 'Missing required fields'}), 400

        if feedback_type not in ['like', 'dislike', 'not_interested']:
            return jsonify({'error': 'Invalid feedback type'}), 400

        db = get_db()

        # Insert or update feedback
        cursor = db.execute("""
            INSERT OR REPLACE INTO recommendations_feedback
            (user_id, video_id, feedback_type, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, video_id, feedback_type, datetime.now()))

        db.commit()

        return jsonify({
            'success': True,
            'message': 'Feedback recorded successfully'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@recommendations_api.route('/api/watch-history', methods=['POST'])
def record_watch():
    """Record a video watch event"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        video_id = data.get('video_id')
        watch_duration = data.get('watch_duration', 0)

        if not all([user_id, video_id]):
            return jsonify({'error': 'Missing required fields'}), 400

        db = get_db()

        # Record watch event
        cursor = db.execute("""
            INSERT INTO view_history (user_id, video_id, watched_at, watch_duration)
            VALUES (?, ?, ?, ?)
        """, (user_id, video_id, datetime.now(), watch_duration))

        db.commit()

        return jsonify({
            'success': True,
            'message': 'Watch event recorded successfully'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
