# SPDX-License-Identifier: MIT
from flask import Blueprint, request, render_template, redirect, url_for, flash, g, session
import sqlite3
from datetime import datetime
from bottube_server import get_db

feedback_bp = Blueprint('feedback', __name__)

def init_feedback_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            session_id TEXT,
            first_reaction TEXT NOT NULL,
            understood_purpose TEXT,
            confusion_points TEXT,
            first_video_clicked TEXT,
            would_return TEXT,
            additional_comments TEXT,
            overall_impression TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT
        )
    ''')
    db.commit()

@feedback_bp.route('/feedback', methods=['GET', 'POST'])
def collect_feedback():
    if request.method == 'POST':
        return handle_feedback_submission()

    return render_template('feedback_form.html')

def handle_feedback_submission():
    # Get form data
    first_reaction = request.form.get('first_reaction', '').strip()
    understood_purpose = request.form.get('understood_purpose', '').strip()
    confusion_points = request.form.get('confusion_points', '').strip()
    first_video = request.form.get('first_video_clicked', '').strip()
    would_return = request.form.get('would_return', '').strip()
    additional_comments = request.form.get('additional_comments', '').strip()
    overall_impression = request.form.get('overall_impression', '').strip()

    # Validation
    errors = []
    if len(overall_impression) < 50:
        errors.append('Overall impression must be at least 50 words.')

    if not first_reaction:
        errors.append('Please share your first reaction.')

    if not understood_purpose:
        errors.append('Please tell us if you understood what BoTTube is.')

    if errors:
        for error in errors:
            flash(error, 'error')
        return render_template('feedback_form.html')

    # Store feedback
    db = get_db()
    user_id = getattr(g, 'user', {}).get('id') if hasattr(g, 'user') else None
    session_id = session.get('session_id', request.remote_addr)
    ip_address = request.remote_addr

    db.execute('''
        INSERT INTO feedback (
            user_id, session_id, first_reaction, understood_purpose,
            confusion_points, first_video_clicked, would_return,
            additional_comments, overall_impression, ip_address
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, session_id, first_reaction, understood_purpose,
        confusion_points, first_video, would_return,
        additional_comments, overall_impression, ip_address
    ))
    db.commit()

    flash('Thank you for your feedback! Your insights help us improve BoTTube.', 'success')
    return redirect(url_for('main.index'))

@feedback_bp.route('/feedback/admin')
def feedback_admin():
    # Simple auth check - in production, use proper admin authentication
    if not session.get('is_admin'):
        return redirect(url_for('main.login'))

    db = get_db()
    feedback_items = db.execute('''
        SELECT * FROM feedback
        ORDER BY timestamp DESC
    ''').fetchall()

    # Calculate basic stats
    total_feedback = len(feedback_items)

    return render_template('feedback_admin.html',
                         feedback_items=feedback_items,
                         total_feedback=total_feedback)
