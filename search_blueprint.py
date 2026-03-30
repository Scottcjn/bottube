"""
BoTTube Video Discoverability Features
Implements bounty #2159 / issue #425
Features: Full-text search, category filters, tag system, trending, For You feed, agent directory
"""

import sqlite3
import json
import re
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request, g
from functools import wraps

search_bp = Blueprint('search', __name__, url_prefix='/discover')

# Predefined categories matching CATEGORY_LIMITS in main server
VIDEO_CATEGORIES = [
    'music', 'film', 'education', 'comedy', 'vlog', 'science-tech',
    'gaming', 'science', 'retro', 'robots', 'creative', 'experimental',
    'news', 'weather', 'other'
]


def get_db():
    """Get database connection from Flask app context or create new one."""
    if 'db' in g:
        return g.db
    from pathlib import Path
    db = sqlite3.connect(str(Path(__file__).parent / "bottube.db"))
    db.row_factory = sqlite3.Row
    return db


@search_bp.route('/')
def discover_page():
    """Main discoverability page with search, filters, and trending."""
    return render_template('discover.html', categories=VIDEO_CATEGORIES)


@search_bp.route('/api/search')
def api_search():
    """
    Full-text search across video titles, descriptions, and tags.
    Query params:
    - q: search query
    - category: filter by category (optional)
    - sort: 'relevance', 'newest', 'views', 'likes' (default: relevance)
    - limit: max results (default: 20, max: 50)
    - offset: pagination offset (default: 0)
    """
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    sort = request.args.get('sort', 'relevance')
    limit = min(int(request.args.get('limit', 20)), 50)
    offset = int(request.args.get('offset', 0))
    
    if not query and not category:
        return jsonify({"error": "Query or category required"}), 400
    
    db = get_db()
    
    # Build the query
    where_clauses = []
    params = []
    
    if query:
        # Search in title, description, tags
        search_term = f"%{query}%"
        where_clauses.append("""(v.title LIKE ? OR v.description LIKE ? OR v.tags LIKE ?)""")
        params.extend([search_term, search_term, search_term])
    
    if category and category in VIDEO_CATEGORIES:
        where_clauses.append("v.category = ?")
        params.append(category)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    # Sort order
    if sort == 'newest':
        order_sql = "v.created_at DESC"
    elif sort == 'views':
        order_sql = "v.views DESC"
    elif sort == 'likes':
        order_sql = "v.likes DESC"
    else:  # relevance - combine multiple factors
        order_sql = "(v.views * 2 + v.likes * 3) DESC"
    
    # Count total
    count_sql = f"SELECT COUNT(*) FROM videos v WHERE {where_sql}"
    total = db.execute(count_sql, params).fetchone()[0]
    
    # Get results
    sql = f"""SELECT 
            v.id,
            v.video_id,
            v.title,
            v.description,
            v.thumbnail,
            v.views,
            v.likes,
            v.tags,
            v.category,
            v.duration_sec,
            v.created_at,
            a.agent_name,
            a.display_name
        FROM videos v
        JOIN agents a ON v.agent_id = a.id
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?"""
    
    results = db.execute(sql, params + [limit, offset]).fetchall()
    
    videos = []
    for row in results:
        try:
            tags = json.loads(row['tags']) if row['tags'] else []
        except:
            tags = []
        
        videos.append({
            "id": row['video_id'],
            "title": row['title'],
            "description": row['description'][:200] + "..." if len(row['description']) > 200 else row['description'],
            "thumbnail": row['thumbnail'],
            "views": row['views'],
            "likes": row['likes'],
            "tags": tags,
            "category": row['category'],
            "duration": round(row['duration_sec'], 1) if row['duration_sec'] else 0,
            "created_at": datetime.fromtimestamp(row['created_at']).isoformat(),
            "agent": {
                "name": row['agent_name'],
                "display_name": row['display_name'] or row['agent_name']
            }
        })
    
    return jsonify({
        "query": query,
        "category": category,
        "sort": sort,
        "total": total,
        "offset": offset,
        "limit": limit,
        "videos": videos
    })


@search_bp.route('/api/categories')
def api_categories():
    """Get all video categories with video counts."""
    db = get_db()
    
    categories = []
    for cat in VIDEO_CATEGORIES:
        count = db.execute(
            "SELECT COUNT(*) FROM videos WHERE category = ?",
            (cat,)
        ).fetchone()[0]
        categories.append({
            "id": cat,
            "name": cat.replace('-', ' ').title(),
            "count": count
        })
    
    # Sort by count descending
    categories.sort(key=lambda x: x['count'], reverse=True)
    
    return jsonify({"categories": categories})


@search_bp.route('/api/tags')
def api_tags():
    """
    Get popular tags with counts.
    Query params:
    - limit: max tags to return (default: 50)
    """
    limit = min(int(request.args.get('limit', 50)), 100)
    
    db = get_db()
    
    # Get all tags from videos
    videos = db.execute("SELECT tags FROM videos WHERE tags != '[]' AND tags != ''").fetchall()
    
    tag_counts = {}
    for row in videos:
        try:
            tags = json.loads(row['tags']) if row['tags'] else []
            for tag in tags:
                tag = tag.lower().strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        except:
            continue
    
    # Sort by count and get top N
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    return jsonify({
        "tags": [{"name": tag, "count": count} for tag, count in sorted_tags]
    })


@search_bp.route('/api/tag/<tag_name>')
def api_videos_by_tag(tag_name):
    """Get videos by specific tag."""
    limit = min(int(request.args.get('limit', 20)), 50)
    offset = int(request.args.get('offset', 0))
    
    db = get_db()
    
    # Search for tag in tags JSON
    search_pattern = f'%"{tag_name.lower()}"%'
    
    total = db.execute(
        "SELECT COUNT(*) FROM videos WHERE LOWER(tags) LIKE ?",
        (search_pattern,)
    ).fetchone()[0]
    
    results = db.execute("""SELECT 
            v.id,
            v.video_id,
            v.title,
            v.description,
            v.thumbnail,
            v.views,
            v.likes,
            v.tags,
            v.category,
            v.duration_sec,
            v.created_at,
            a.agent_name,
            a.display_name
        FROM videos v
        JOIN agents a ON v.agent_id = a.id
        WHERE LOWER(v.tags) LIKE ?
        ORDER BY v.created_at DESC
        LIMIT ? OFFSET ?""",
        (search_pattern, limit, offset)
    ).fetchall()
    
    videos = []
    for row in results:
        try:
            tags = json.loads(row['tags']) if row['tags'] else []
        except:
            tags = []
        
        videos.append({
            "id": row['video_id'],
            "title": row['title'],
            "thumbnail": row['thumbnail'],
            "views": row['views'],
            "likes": row['likes'],
            "tags": tags,
            "category": row['category'],
            "duration": round(row['duration_sec'], 1) if row['duration_sec'] else 0,
            "created_at": datetime.fromtimestamp(row['created_at']).isoformat(),
            "agent": {
                "name": row['agent_name'],
                "display_name": row['display_name'] or row['agent_name']
            }
        })
    
    return jsonify({
        "tag": tag_name,
        "total": total,
        "offset": offset,
        "limit": limit,
        "videos": videos
    })


@search_bp.route('/api/trending')
def api_trending():
    """
    Get trending videos based on recent views + engagement velocity.
    Uses formula: (views_24h * 2 + comments_24h * 5) for recency weighting.
    """
    limit = min(int(request.args.get('limit', 20)), 50)
    
    db = get_db()
    
    # Calculate 24h ago timestamp
    day_ago = (datetime.now() - timedelta(hours=24)).timestamp()
    
    # Get trending scores
    trending = db.execute("""SELECT 
            v.id,
            v.video_id,
            v.title,
            v.thumbnail,
            v.views,
            v.likes,
            v.category,
            v.duration_sec,
            v.created_at,
            a.agent_name,
            a.display_name,
            COALESCE(vc.recent_views, 0) * 2 + COALESCE(cc.recent_comments, 0) * 5 as trending_score
        FROM videos v
        JOIN agents a ON v.agent_id = a.id
        LEFT JOIN (
            SELECT video_id, COUNT(*) as recent_views 
            FROM views 
            WHERE created_at >= ? 
            GROUP BY video_id
        ) vc ON vc.video_id = v.video_id
        LEFT JOIN (
            SELECT video_id, COUNT(*) as recent_comments
            FROM comments
            WHERE created_at >= ?
            GROUP BY video_id
        ) cc ON cc.video_id = v.video_id
        WHERE trending_score > 0
        ORDER BY trending_score DESC
        LIMIT ?""", (day_ago, day_ago, limit)).fetchall()
    
    videos = []
    for row in trending:
        videos.append({
            "id": row['video_id'],
            "title": row['title'],
            "thumbnail": row['thumbnail'],
            "views": row['views'],
            "likes": row['likes'],
            "category": row['category'],
            "duration": round(row['duration_sec'], 1) if row['duration_sec'] else 0,
            "trending_score": row['trending_score'],
            "created_at": datetime.fromtimestamp(row['created_at']).isoformat(),
            "agent": {
                "name": row['agent_name'],
                "display_name": row['display_name'] or row['agent_name']
            }
        })
    
    return jsonify({"videos": videos})


@search_bp.route('/api/for-you')
def api_for_you():
    """
    Personalized "For You" feed based on viewing history.
    Authenticate via X-API-Key header to get personalized results.
    Falls back to trending if no key provided.
    """
    limit = min(int(request.args.get('limit', 20)), 50)

    # Authenticate agent via API key header (not raw agent_id param)
    api_key = request.headers.get('X-API-Key', '').strip()
    agent_id = None
    if api_key:
        db_check = get_db()
        agent_row = db_check.execute(
            "SELECT id FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if agent_row:
            agent_id = agent_row['id']

    if not agent_id:
        # Return popular videos if not authenticated
        return api_trending()
    
    db = get_db()
    
    # Get categories and tags the agent has viewed
    viewed = db.execute("""SELECT DISTINCT v.category, v.tags
        FROM views vw
        JOIN videos v ON vw.video_id = v.video_id
        WHERE vw.agent_id = ?""", (agent_id,)).fetchall()
    
    categories = set()
    tags = set()
    for row in viewed:
        if row['category']:
            categories.add(row['category'])
        try:
            video_tags = json.loads(row['tags']) if row['tags'] else []
            tags.update(t.lower() for t in video_tags)
        except:
            pass
    
    if not categories and not tags:
        # New user - return trending
        return api_trending()
    
    # Build recommendation query using parameterized SQL
    # Each CASE uses a parameter placeholder instead of string interpolation
    score_parts = []
    params = []

    for cat in categories:
        score_parts.append("CASE WHEN v.category = ? THEN 3 ELSE 0 END")
        params.append(cat)

    # Tag matching (parameterized LIKE)
    for tag in list(tags)[:10]:
        score_parts.append("CASE WHEN LOWER(v.tags) LIKE ? THEN 2 ELSE 0 END")
        params.append(f'%"{tag}"%')

    # Recency score (parameterized timestamp)
    week_ago = (datetime.now() - timedelta(days=7)).timestamp()
    score_parts.append("CASE WHEN v.created_at >= ? THEN 5 ELSE 0 END")
    params.append(week_ago)

    # General popularity (no user input, safe as-is)
    score_parts.append("v.views * 0.001")
    score_parts.append("v.likes * 0.01")

    score_sql = " + ".join(score_parts) if score_parts else "0"

    # Exclude already viewed (parameterized)
    viewed_ids = db.execute(
        "SELECT DISTINCT video_id FROM views WHERE agent_id = ?",
        (agent_id,)
    ).fetchall()
    viewed_id_list = [v[0] for v in viewed_ids]

    exclude_sql = ""
    if viewed_id_list:
        placeholders = ", ".join("?" for _ in viewed_id_list)
        exclude_sql = f"AND v.video_id NOT IN ({placeholders})"
        params.extend(viewed_id_list)

    params.append(limit)

    sql = f"""SELECT
            v.id,
            v.video_id,
            v.title,
            v.description,
            v.thumbnail,
            v.views,
            v.likes,
            v.tags,
            v.category,
            v.duration_sec,
            v.created_at,
            a.agent_name,
            a.display_name,
            ({score_sql}) as recommendation_score
        FROM videos v
        JOIN agents a ON v.agent_id = a.id
        WHERE 1=1 {exclude_sql}
        ORDER BY recommendation_score DESC
        LIMIT ?"""

    results = db.execute(sql, params).fetchall()
    
    videos = []
    for row in results:
        try:
            tags = json.loads(row['tags']) if row['tags'] else []
        except:
            tags = []
        
        videos.append({
            "id": row['video_id'],
            "title": row['title'],
            "description": row['description'][:150] + "..." if len(row['description']) > 150 else row['description'],
            "thumbnail": row['thumbnail'],
            "views": row['views'],
            "likes": row['likes'],
            "tags": tags,
            "category": row['category'],
            "duration": round(row['duration_sec'], 1) if row['duration_sec'] else 0,
            "score": round(row['recommendation_score'], 2),
            "created_at": datetime.fromtimestamp(row['created_at']).isoformat(),
            "agent": {
                "name": row['agent_name'],
                "display_name": row['display_name'] or row['agent_name']
            }
        })
    
    return jsonify({
        "personalized": len(videos) > 0,
        "based_on": {
            "categories": list(categories),
            "tags": list(tags)[:10]
        },
        "videos": videos
    })


@search_bp.route('/api/agents')
def api_agent_directory():
    """
    Browse agents by capability, subscriber count, or activity.
    Query params:
    - sort: 'subscribers', 'videos', 'recent' (default: subscribers)
    - limit: max results (default: 20)
    """
    sort = request.args.get('sort', 'subscribers')
    limit = min(int(request.args.get('limit', 20)), 50)
    
    db = get_db()
    
    # Build sort clause
    if sort == 'videos':
        order_sql = "video_count DESC"
    elif sort == 'recent':
        order_sql = "last_upload DESC"
    else:  # subscribers
        order_sql = "subscriber_count DESC"
    
    agents = db.execute(f"""SELECT 
            a.id,
            a.agent_name,
            a.display_name,
            a.avatar_url,
            a.bio,
            COALESCE(s.subscriber_count, 0) as subscriber_count,
            COALESCE(v.video_count, 0) as video_count,
            COALESCE(v.last_upload, 0) as last_upload
        FROM agents a
        LEFT JOIN (
            SELECT channel_id, COUNT(*) as subscriber_count 
            FROM subscriptions GROUP BY channel_id
        ) s ON s.channel_id = a.id
        LEFT JOIN (
            SELECT agent_id, COUNT(*) as video_count, MAX(created_at) as last_upload
            FROM videos GROUP BY agent_id
        ) v ON v.agent_id = a.id
        WHERE video_count > 0
        ORDER BY {order_sql}
        LIMIT ?""", (limit,)).fetchall()
    
    results = []
    for row in agents:
        results.append({
            "id": row['id'],
            "name": row['agent_name'],
            "display_name": row['display_name'] or row['agent_name'],
            "avatar": row['avatar_url'],
            "bio": row['bio'][:150] + "..." if row['bio'] and len(row['bio']) > 150 else row['bio'],
            "subscribers": row['subscriber_count'],
            "videos": row['video_count'],
            "last_upload": datetime.fromtimestamp(row['last_upload']).isoformat() if row['last_upload'] else None
        })
    
    return jsonify({
        "sort": sort,
        "agents": results
    })
