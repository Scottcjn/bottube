from flask import Blueprint, request, jsonify, session, g, render_template
from db import get_db
import sqlite3
import json
from datetime import datetime

tv_bp = Blueprint('tv', __name__, url_prefix='/tv')


@tv_bp.route('/home')
def tv_home():
    """TV home screen with featured content"""
    db = get_db()
    cursor = db.cursor()

    # Get trending videos (most viewed in last 7 days)
    cursor.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.created_at > datetime('now', '-7 days')
        ORDER BY v.view_count DESC
        LIMIT 20
    ''')
    trending = cursor.fetchall()

    # Get recent videos
    cursor.execute('''
        SELECT v.id, v.title, v.description, v.thumbnail_url, v.duration,
               u.username, v.view_count, v.created_at
        FROM videos v
        JOIN users u ON v.user_id = u.id
        ORDER BY v.created_at DESC
        LIMIT 20
    ''')
    recent = cursor.fetchall()

    trending_list = []
    for row in trending:
        trending_list.append({
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'thumbnail_url': row[3],
            'duration': row[4],
            'username': row[5],
            'view_count': row[6],
            'created_at': row[7]
        })

    recent_list = []
    for row in recent:
        recent_list.append({
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'thumbnail_url': row[3],
            'duration': row[4],
            'username': row[5],
            'view_count': row[6],
            'created_at': row[7]
        })

    return jsonify({
        'trending': trending_list,
        'recent': recent_list
    })


@tv_bp.route('/categories')
def tv_categories():
    """Get available video categories for TV browsing"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT DISTINCT category
        FROM videos
        WHERE category IS NOT NULL AND category != ''
        ORDER BY category
    ''')
    categories = [row[0] for row in cursor.fetchall()]

    return jsonify({'categories': categories})
