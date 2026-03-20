from flask import Blueprint, render_template, request, redirect, url_for, flash, g
import sqlite3
from datetime import datetime

feedback_bp = Blueprint('feedback', __name__)

def get_db():
    """Get database connection using the same pattern as bottube_server.py"""
    if 'db' not in g:
        g.db = sqlite3.connect('bottube.db')
        g.db.row_factory = sqlite3.Row
    return g.db

def init_feedback_db():
    """Initialize feedback tables"""
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            first_reaction TEXT NOT NULL,
            understood_service BOOLEAN NOT NULL,
            confusion_points TEXT,
            first_video_clicked TEXT,
            first_video_reason TEXT,
            would_return BOOLEAN NOT NULL,
            return_reason TEXT,
            additional_comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    db.commit()

@feedback_bp.route('/feedback', methods=['GET', 'POST'])
def collect_feedback():
    if request.method == 'POST':
        # Extract form data
        first_reaction = request.form.get('first_reaction', '').strip()
        understood_service = request.form.get('understood_service') == 'yes'
        confusion_points = request.form.get('confusion_points', '').strip()
        first_video_clicked = request.form.get('first_video_clicked', '').strip()
        first_video_reason = request.form.get('first_video_reason', '').strip()
        would_return = request.form.get('would_return') == 'yes'
        return_reason = request.form.get('return_reason', '').strip()
        additional_comments = request.form.get('additional_comments', '').strip()

        # Validate minimum word count (50 words total across all text fields)
        total_text = f"{first_reaction} {confusion_points} {first_video_reason} {return_reason} {additional_comments}"
        word_count = len(total_text.split())

        if word_count < 50:
            flash('Please provide at least 50 words of feedback total.', 'error')
            return render_template('feedback_form.html')

        if not first_reaction:
            flash('Please share your first reaction.', 'error')
            return render_template('feedback_form.html')

        # Save to database
        db = get_db()
        user_id = g.user['id'] if hasattr(g, 'user') and g.user else None
        ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)

        db.execute('''
            INSERT INTO feedback (
                user_id, first_reaction, understood_service, confusion_points,
                first_video_clicked, first_video_reason, would_return,
                return_reason, additional_comments, ip_address
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, first_reaction, understood_service, confusion_points,
            first_video_clicked, first_video_reason, would_return,
            return_reason, additional_comments, ip_address
        ))
        db.commit()

        flash('Thank you for your feedback! Your honest opinion helps us improve.', 'success')
        return redirect(url_for('main.index'))

    return render_template('feedback_form.html')

@feedback_bp.route('/admin/feedback')
def admin_feedback():
    """Admin view for all feedback submissions"""
    if not hasattr(g, 'user') or not g.user or not g.user.get('is_admin'):
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.index'))

    db = get_db()
    feedback_entries = db.execute('''
        SELECT f.*, u.username
        FROM feedback f
        LEFT JOIN users u ON f.user_id = u.id
        ORDER BY f.created_at DESC
    ''').fetchall()

    return render_template('admin_feedback.html', feedback_entries=feedback_entries)

@feedback_bp.route('/admin/feedback/<int:feedback_id>')
def view_feedback_detail(feedback_id):
    """View detailed feedback entry"""
    if not hasattr(g, 'user') or not g.user or not g.user.get('is_admin'):
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.index'))

    db = get_db()
    feedback_entry = db.execute('''
        SELECT f.*, u.username, u.email
        FROM feedback f
        LEFT JOIN users u ON f.user_id = u.id
        WHERE f.id = ?
    ''', (feedback_id,)).fetchone()

    if not feedback_entry:
        flash('Feedback entry not found.', 'error')
        return redirect(url_for('feedback.admin_feedback'))

    return render_template('feedback_detail.html', feedback=feedback_entry)
