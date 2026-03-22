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

    # Find users who watched similar videos
    cursor = db.execute("""
        SELECT user_id, COUNT(DISTINCT video_id) as overlap
        FROM view_history
        WHERE video_id IN ({}) AND user_id != ?
        GROUP BY user_id
        HAVING overlap >= ?
        ORDER BY overlap DESC
        LIMIT 20
    """.format(','.join('?' * len(user_videos))), list(user_videos) + [user_id, min_overlap])

    return cursor.fetchall()


def collaborative_filtering_recommendations(user_id, limit=10):
    """Get recommendations based on collaborative filtering"""
    similar_users = get_similar_users(user_id)
    if not similar_users:
        return []

    db = get_db()

    # Get videos watched by current user to exclude them
    cursor = db.execute("""
        SELECT video_id FROM view_history WHERE user_id = ?
    """, (user_id,))
    watched_videos = {row['video_id'] for row in cursor.fetchall()}

    # Get recommendations from similar users
    similar_user_ids = [str(row['user_id']) for row in similar_users]

    cursor = db.execute("""
        SELECT v.id, v.title, v.description, v.upload_date, v.category,
               COUNT(*) as recommendation_score
        FROM view_history vh
        JOIN videos v ON vh.video_id = v.id
        WHERE vh.user_id IN ({}) AND vh.video_id NOT IN ({})
        GROUP BY v.id
        ORDER BY recommendation_score DESC, v.upload_date DESC
        LIMIT ?
    """.format(
        ','.join('?' * len(similar_user_ids)),
        ','.join('?' * len(watched_videos)) if watched_videos else '0'
    ), similar_user_ids + list(watched_videos) + [limit])

    return cursor.fetchall()


def content_based_recommendations(user_id, limit=10):
    """Get recommendations based on content similarity"""
    watch_history = get_user_watch_history(user_id, limit=20)
    if not watch_history:
        return []

    # Extract user preferences
    user_categories = Counter()
    user_keywords = Counter()

    for video in watch_history:
        if video['category']:
            user_categories[video['category']] += 1

        # Extract keywords from title and description
        title_keywords = extract_keywords(video['title'])
        desc_keywords = extract_keywords(video['description'])
        tag_keywords = extract_keywords(video['tags'])

        for keyword in title_keywords | desc_keywords | tag_keywords:
            user_keywords[keyword] += 1

    # Get top preferences
    top_categories = [cat for cat, _ in user_categories.most_common(3)]
    top_keywords = [kw for kw, _ in user_keywords.most_common(10)]

    if not top_categories and not top_keywords:
        return []

    db = get_db()

    # Get videos watched by user to exclude them
    cursor = db.execute("""
        SELECT video_id FROM view_history WHERE user_id = ?
    """, (user_id,))
    watched_videos = {row['video_id'] for row in cursor.fetchall()}

    # Build query for content-based recommendations
    conditions = []
    params = []

    if top_categories:
        category_conditions = ' OR '.join(['v.category = ?'] * len(top_categories))
        conditions.append(f'({category_conditions})')
        params.extend(top_categories)

    if top_keywords:
        keyword_conditions = []
        for keyword in top_keywords:
            keyword_conditions.append('(v.title LIKE ? OR v.description LIKE ? OR v.tags LIKE ?)')
            keyword_pattern = f'%{keyword}%'
            params.extend([keyword_pattern, keyword_pattern, keyword_pattern])
        conditions.append(f'({" OR ".join(keyword_conditions)})')

    if watched_videos:
        exclude_condition = f'v.id NOT IN ({",".join(["?"] * len(watched_videos))})'n        conditions.append(exclude_condition)
        params.extend(list(watched_videos))

    where_clause = ' AND '.join(conditions)

    cursor = db.execute("""
        SELECT v.id, v.title, v.description, v.upload_date, v.category
        FROM videos v
        WHERE {}
        ORDER BY v.upload_date DESC
        LIMIT ?
    """.format(where_clause), params + [limit])

    return cursor.fetchall()


def get_trending_videos(period='week', limit=10):
    """Get trending videos based on recent view activity"""
    db = get_db()

    # Calculate time window
    if period == 'day':
        hours = 24
    elif period == 'week':
        hours = 24 * 7
    else:  # month
        hours = 24 * 30

    cutoff_time = datetime.now() - timedelta(hours=hours)

    cursor = db.execute("""
        SELECT v.id, v.title, v.description, v.upload_date, v.category,
               COUNT(vh.id) as view_count,
               COUNT(DISTINCT vh.user_id) as unique_viewers
        FROM videos v
        LEFT JOIN view_history vh ON v.id = vh.video_id
            AND vh.watched_at >= ?
        GROUP BY v.id
        HAVING view_count > 0
        ORDER BY view_count DESC, unique_viewers DESC
        LIMIT ?
    """, (cutoff_time, limit))

    return cursor.fetchall()


@recommendations_api.route('/api/recommendations/<int:user_id>')
def get_recommendations(user_id):
    """Main recommendations endpoint"""
    try:
        recommendation_type = request.args.get('type', 'mixed')
        limit = min(int(request.args.get('limit', 20)), 50)

        recommendations = []

        if recommendation_type in ['mixed', 'collaborative']:
            collab_recs = collaborative_filtering_recommendations(user_id, limit // 2)
            recommendations.extend([{
                'id': rec['id'],
                'title': rec['title'],
                'description': rec['description'],
                'upload_date': rec['upload_date'],
                'category': rec['category'],
                'score': rec.get('recommendation_score', 0),
                'type': 'collaborative'
            } for rec in collab_recs])

        if recommendation_type in ['mixed', 'content']:
            content_recs = content_based_recommendations(user_id, limit // 2)
            recommendations.extend([{
                'id': rec['id'],
                'title': rec['title'],
                'description': rec['description'],
                'upload_date': rec['upload_date'],
                'category': rec['category'],
                'score': 1,
                'type': 'content'
            } for rec in content_recs])

        # Remove duplicates while preserving order
        seen_ids = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec['id'] not in seen_ids:
                seen_ids.add(rec['id'])
                unique_recommendations.append(rec)

        return jsonify({
            'success': True,
            'recommendations': unique_recommendations[:limit],
            'total': len(unique_recommendations)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@recommendations_api.route('/api/trending')
def get_trending():
    """Get trending videos"""
    try:
        period = request.args.get('period', 'week')
        limit = min(int(request.args.get('limit', 20)), 50)

        trending = get_trending_videos(period, limit)

        return jsonify({
            'success': True,
            'trending': [{
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'upload_date': video['upload_date'],
                'category': video['category'],
                'view_count': video['view_count'],
                'unique_viewers': video['unique_viewers']
            } for video in trending],
            'period': period
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@recommendations_api.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Submit user feedback on recommendations"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        video_id = data.get('video_id')
        feedback_type = data.get('feedback_type')  # 'like', 'dislike', 'not_interested'

        if not all([user_id, video_id, feedback_type]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400

        if feedback_type not in ['like', 'dislike', 'not_interested']:
            return jsonify({
                'success': False,
                'error': 'Invalid feedback type'
            }), 400

        db = get_db()

        # Insert or update feedback
        db.execute("""
            INSERT OR REPLACE INTO recommendations_feedback
            (user_id, video_id, feedback_type, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, video_id, feedback_type, datetime.now()))

        db.commit()

        return jsonify({
            'success': True,
            'message': 'Feedback submitted successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@recommendations_api.route('/api/watch-history', methods=['POST'])
def record_watch():
    """Record a video watch event"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        video_id = data.get('video_id')
        watch_duration = data.get('watch_duration', 0)

        if not all([user_id, video_id]):
            return jsonify({
                'success': False,
                'error': 'Missing user_id or video_id'
            }), 400

        db = get_db()

        # Record watch event
        db.execute("""
            INSERT OR IGNORE INTO view_history
            (user_id, video_id, watched_at, watch_duration)
            VALUES (?, ?, ?, ?)
        """, (user_id, video_id, datetime.now(), watch_duration))

        db.commit()

        return jsonify({
            'success': True,
            'message': 'Watch recorded successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
