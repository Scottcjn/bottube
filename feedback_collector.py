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
        return render_template('feedback_form.html',
                             first_reaction=first_reaction,
                             understood_purpose=understood_purpose,
                             confusion_points=confusion_points,
                             first_video=first_video,
                             would_return=would_return,
                             additional_comments=additional_comments,
                             overall_impression=overall_impression)

    # Store in database
    try:
        db = get_db()
        user_id = g.user.get('id') if g.user else None
        session_id = session.get('session_id', request.cookies.get('session'))
        ip_addr = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)

        db.execute('''
            INSERT INTO feedback (user_id, session_id, first_reaction, understood_purpose,
                                confusion_points, first_video_clicked, would_return,
                                additional_comments, overall_impression, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, session_id, first_reaction, understood_purpose,
              confusion_points, first_video, would_return, additional_comments,
              overall_impression, ip_addr))
        db.commit()

        flash('Thank you for your feedback! Your insights help us improve BoTTube.', 'success')
        return redirect(url_for('index'))

    except sqlite3.Error as e:
        flash('Sorry, there was an error saving your feedback. Please try again.', 'error')
        return render_template('feedback_form.html',
                             first_reaction=first_reaction,
                             understood_purpose=understood_purpose,
                             confusion_points=confusion_points,
                             first_video=first_video,
                             would_return=would_return,
                             additional_comments=additional_comments,
                             overall_impression=overall_impression)

@feedback_bp.route('/admin/feedback')
def view_feedback():
    # Basic admin check - you might want to implement proper admin auth
    if not g.user or not g.user.get('is_admin'):
        flash('Access denied.', 'error')
        return redirect(url_for('index'))

    db = get_db()
    feedback_entries = db.execute('''
        SELECT id, user_id, first_reaction, understood_purpose, confusion_points,
               first_video_clicked, would_return, additional_comments,
               overall_impression, timestamp, ip_address
        FROM feedback
        ORDER BY timestamp DESC
    ''').fetchall()

    return render_template('admin_feedback.html', feedback_entries=feedback_entries)

@feedback_bp.route('/admin/feedback/<int:feedback_id>')
def view_single_feedback(feedback_id):
    if not g.user or not g.user.get('is_admin'):
        flash('Access denied.', 'error')
        return redirect(url_for('index'))

    db = get_db()
    feedback = db.execute('''
        SELECT * FROM feedback WHERE id = ?
    ''', (feedback_id,)).fetchone()

    if not feedback:
        flash('Feedback not found.', 'error')
        return redirect(url_for('feedback.view_feedback'))

    return render_template('feedback_detail.html', feedback=feedback)

# Initialize the feedback database when the module is imported
init_feedback_db()
