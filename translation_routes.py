from flask import Blueprint, render_template, request, jsonify, g, session
from bottube_server import get_db, require_auth
import sqlite3
import json

translation_bp = Blueprint('translation', __name__)

@translation_bp.route('/translations')
def translations_page():
    db = get_db()
    
    # Get all available languages
    languages = db.execute('''
        SELECT DISTINCT language FROM video_translations 
        WHERE language IS NOT NULL AND language != ""
        ORDER BY language
    ''').fetchall()
    
    # Get recent translations
    recent_translations = db.execute('''
        SELECT vt.*, v.original_title, v.original_description, v.video_id
        FROM video_translations vt
        JOIN videos v ON vt.video_id = v.id
        ORDER BY vt.created_at DESC
        LIMIT 20
    ''').fetchall()
    
    return render_template('translations.html', 
                         languages=languages,
                         recent_translations=recent_translations)

@translation_bp.route('/api/translations/<int:video_id>')
def get_translations(video_id):
    db = get_db()
    
    translations = db.execute('''
        SELECT language, title, description, translator_id, created_at
        FROM video_translations 
        WHERE video_id = ?
        ORDER BY created_at DESC
    ''', (video_id,)).fetchall()
    
    return jsonify([dict(t) for t in translations])

@translation_bp.route('/api/translations/<int:video_id>/<language>')
def get_translation_by_language(video_id, language):
    db = get_db()
    
    translation = db.execute('''
        SELECT * FROM video_translations 
        WHERE video_id = ? AND language = ?
        ORDER BY created_at DESC
        LIMIT 1
    ''', (video_id, language)).fetchone()
    
    if translation:
        return jsonify(dict(translation))
    return jsonify({'error': 'Translation not found'}), 404

@translation_bp.route('/api/translations', methods=['POST'])
@require_auth
def add_translation():
    data = request.get_json()
    
    if not all(k in data for k in ['video_id', 'language', 'title', 'description']):
        return jsonify({'error': 'Missing required fields'}), 400
    
    db = get_db()
    
    # Check if translation already exists
    existing = db.execute('''
        SELECT id FROM video_translations 
        WHERE video_id = ? AND language = ? AND translator_id = ?
    ''', (data['video_id'], data['language'], g.user['id'])).fetchone()
    
    if existing:
        # Update existing translation
        db.execute('''
            UPDATE video_translations 
            SET title = ?, description = ?, created_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (data['title'], data['description'], existing['id']))
    else:
        # Create new translation
        db.execute('''
            INSERT INTO video_translations (video_id, language, title, description, translator_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (data['video_id'], data['language'], data['title'], data['description'], g.user['id']))
    
    db.commit()
    return jsonify({'success': True})

@translation_bp.route('/api/videos/translated/<language>')
def get_videos_by_language(language):
    db = get_db()
    
    videos = db.execute('''
        SELECT v.*, vt.title as translated_title, vt.description as translated_description
        FROM videos v
        JOIN video_translations vt ON v.id = vt.video_id
        WHERE vt.language = ?
        ORDER BY vt.created_at DESC
    ''', (language,)).fetchall()
    
    return jsonify([dict(v) for v in videos])

@translation_bp.route('/api/languages')
def get_supported_languages():
    languages = [
        'Chinese', 'Spanish', 'Portuguese', 'French', 'Japanese', 
        'Korean', 'German', 'Russian', 'Arabic', 'Hindi'
    ]
    return jsonify(languages)