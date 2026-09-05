# SPDX-License-Identifier: MIT
from flask import Blueprint, render_template, request, jsonify, g, session
from bottube_server import get_db, require_api_key
import sqlite3
import json

translation_bp = Blueprint('translation', __name__)


def init_translation_tables(db):
    """Create the durable translation store on the canonical BoTTube database."""
    db.execute('''
        CREATE TABLE IF NOT EXISTS video_translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            language TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            translator_id INTEGER NOT NULL,
            created_at REAL NOT NULL DEFAULT (unixepoch()),
            UNIQUE(video_id, language, translator_id),
            FOREIGN KEY (video_id) REFERENCES videos(video_id),
            FOREIGN KEY (translator_id) REFERENCES agents(id)
        )
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS idx_video_translations_language_created
        ON video_translations(language, created_at DESC)
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS idx_video_translations_video_created
        ON video_translations(video_id, created_at DESC)
    ''')
    db.commit()


def _request_json_object():
    """Parse and return a JSON object from the request body.
    
    Returns:
        The result value.
    """
    data = request.get_json(silent=True)
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, (jsonify({'error': 'JSON object required'}), 400)
    return data, None


@translation_bp.route('/translations')
def translations_page():
    """Handle page for translations."""
    db = get_db()
    
    # Get all available languages
    languages = db.execute('''
        SELECT DISTINCT language FROM video_translations 
        WHERE language IS NOT NULL AND language != ""
        ORDER BY language
    ''').fetchall()
    
    # Get recent translations
    recent_translations = db.execute('''
        SELECT vt.*, v.title AS original_title,
               v.description AS original_description, v.video_id
        FROM video_translations vt
        JOIN videos v ON vt.video_id = v.video_id
        JOIN agents a ON a.id = v.agent_id
        WHERE COALESCE(v.is_removed, 0) = 0
          AND COALESCE(a.is_banned, 0) = 0
        ORDER BY vt.created_at DESC
        LIMIT 20
    ''').fetchall()
    
    return render_template('translations.html', 
                         languages=languages,
                         recent_translations=recent_translations)

@translation_bp.route('/api/translations/<video_id>')
def get_translations(video_id):
    """Retrieve translations.
    
    Args:
        video_id: Parameter value.
    
    Returns:
        The result value.
    """
    db = get_db()
    
    translations = db.execute('''
        SELECT vt.language, vt.title, vt.description, vt.translator_id, vt.created_at
        FROM video_translations vt
        JOIN videos v ON v.video_id = vt.video_id
        JOIN agents a ON a.id = v.agent_id
        WHERE vt.video_id = ?
          AND COALESCE(v.is_removed, 0) = 0
          AND COALESCE(a.is_banned, 0) = 0
        ORDER BY vt.created_at DESC
    ''', (video_id,)).fetchall()
    
    return jsonify([dict(t) for t in translations])

@translation_bp.route('/api/translations/<video_id>/<language>')
def get_translation_by_language(video_id, language):
    """Retrieve translation by language.
    
    Args:
        video_id: Parameter value.
        language: Parameter value.
    """
    db = get_db()
    
    translation = db.execute('''
        SELECT vt.*
        FROM video_translations vt
        JOIN videos v ON v.video_id = vt.video_id
        JOIN agents a ON a.id = v.agent_id
        WHERE vt.video_id = ? AND vt.language = ?
          AND COALESCE(v.is_removed, 0) = 0
          AND COALESCE(a.is_banned, 0) = 0
        ORDER BY vt.created_at DESC
        LIMIT 1
    ''', (video_id, language)).fetchone()
    
    if translation:
        return jsonify(dict(translation))
    return jsonify({'error': 'Translation not found'}), 404

@translation_bp.route('/api/translations', methods=['POST'])
@require_api_key
def add_translation():
    """Add translation.
    
    Returns:
        The result value.
    """
    data, error = _request_json_object()
    if error:
        return error
    
    if not all(k in data for k in ['video_id', 'language', 'title', 'description']):
        return jsonify({'error': 'Missing required fields'}), 400

    video_id = data['video_id']
    language = data['language']
    title = data['title']
    description = data['description']
    if not isinstance(video_id, str) or not video_id.strip() or len(video_id) > 128:
        return jsonify({'error': 'video_id must be a non-empty string'}), 400
    if not isinstance(language, str) or not language.strip() or len(language) > 64:
        return jsonify({'error': 'language must be a non-empty string'}), 400
    if not isinstance(title, str) or not title.strip() or len(title) > 500:
        return jsonify({'error': 'title must be a non-empty string'}), 400
    if not isinstance(description, str) or len(description) > 10000:
        return jsonify({'error': 'description must be a string'}), 400

    video_id = video_id.strip()
    language = language.strip()
    title = title.strip()
    
    db = get_db()
    video = db.execute('''
        SELECT v.video_id
        FROM videos v
        JOIN agents a ON a.id = v.agent_id
        WHERE v.video_id = ?
          AND COALESCE(v.is_removed, 0) = 0
          AND COALESCE(a.is_banned, 0) = 0
    ''', (video_id,)).fetchone()
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    # Check if translation already exists
    existing = db.execute('''
        SELECT id FROM video_translations 
        WHERE video_id = ? AND language = ? AND translator_id = ?
    ''', (video_id, language, g.agent['id'])).fetchone()
    
    if existing:
        # Update existing translation
        db.execute('''
            UPDATE video_translations 
            SET title = ?, description = ?, created_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (title, description, existing['id']))
    else:
        # Create new translation
        db.execute('''
            INSERT INTO video_translations (video_id, language, title, description, translator_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (video_id, language, title, description, g.agent['id']))
    
    db.commit()
    return jsonify({'success': True})

@translation_bp.route('/api/videos/translated/<language>')
def get_videos_by_language(language):
    """Retrieve videos by language.
    
    Args:
        language: Parameter value.
    """
    db = get_db()
    
    videos = db.execute('''
        SELECT v.*, vt.title as translated_title, vt.description as translated_description
        FROM videos v
        JOIN video_translations vt ON v.video_id = vt.video_id
        JOIN agents a ON a.id = v.agent_id
        WHERE vt.language = ?
          AND COALESCE(v.is_removed, 0) = 0
          AND COALESCE(a.is_banned, 0) = 0
        ORDER BY vt.created_at DESC
    ''', (language,)).fetchall()
    
    return jsonify([dict(v) for v in videos])

@translation_bp.route('/api/languages')
def get_supported_languages():
    """Retrieve supported languages.
    
    Returns:
        The result value.
    """
    languages = [
        'Chinese', 'Spanish', 'Portuguese', 'French', 'Japanese', 
        'Korean', 'German', 'Russian', 'Arabic', 'Hindi'
    ]
    return jsonify(languages)
