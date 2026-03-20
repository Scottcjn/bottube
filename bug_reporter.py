import sqlite3
from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

bug_reporter = Blueprint('bug_reporter', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash('Please log in to report bugs.')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('bottube.db')
        g.db.row_factory = sqlite3.Row
    return g.db

def init_bug_reports_table():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS bug_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            steps_to_reproduce TEXT NOT NULL,
            expected_behavior TEXT NOT NULL,
            actual_behavior TEXT NOT NULL,
            browser_info TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    db.commit()

@bug_reporter.route('/report-bug', methods=['GET', 'POST'])
@login_required
def report_bug():
    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        steps = request.form.get('steps_to_reproduce', '').strip()
        expected = request.form.get('expected_behavior', '').strip()
        actual = request.form.get('actual_behavior', '').strip()
        browser_info = request.form.get('browser_info', '').strip()
        severity = request.form.get('severity', 'medium')

        errors = []

        if not url:
            errors.append('URL where the bug occurred is required')
        if not title:
            errors.append('Bug title is required')
        if not description:
            errors.append('Bug description is required')
        if not steps:
            errors.append('Steps to reproduce are required')
        if not expected:
            errors.append('Expected behavior is required')
        if not actual:
            errors.append('Actual behavior is required')
        if not browser_info:
            errors.append('Browser/device information is required')
        if severity not in ['low', 'medium', 'high', 'critical']:
            errors.append('Invalid severity level')

        if len(title) > 200:
            errors.append('Title must be less than 200 characters')
        if len(description) > 2000:
            errors.append('Description must be less than 2000 characters')

        if errors:
            for error in errors:
                flash(error)
            return render_template('bug_report.html')

        try:
            init_bug_reports_table()
            db = get_db()
            cursor = db.execute('''
                INSERT INTO bug_reports
                (user_id, url, title, description, steps_to_reproduce,
                 expected_behavior, actual_behavior, browser_info, severity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (g.user['id'], url, title, description, steps, expected, actual, browser_info, severity))

            bug_id = cursor.lastrowid
            db.commit()

            send_bug_notification(bug_id, title, g.user['username'], severity)

            flash('Bug report submitted successfully! Thank you for helping improve BoTTube.')
            return redirect(url_for('bug_reporter.view_bug', bug_id=bug_id))

        except sqlite3.Error as e:
            flash('Database error occurred. Please try again.')
            return render_template('bug_report.html')

    return render_template('bug_report.html')

@bug_reporter.route('/bug/<int:bug_id>')
def view_bug(bug_id):
    db = get_db()
    bug = db.execute('''
        SELECT br.*, u.username
        FROM bug_reports br
        JOIN users u ON br.user_id = u.id
        WHERE br.id = ?
    ''', (bug_id,)).fetchone()

    if not bug:
        flash('Bug report not found.')
        return redirect(url_for('bug_reporter.list_bugs'))

    return render_template('bug_detail.html', bug=bug)

@bug_reporter.route('/bugs')
def list_bugs():
    db = get_db()
    status_filter = request.args.get('status', 'all')
    severity_filter = request.args.get('severity', 'all')

    query = '''
        SELECT br.*, u.username
        FROM bug_reports br
        JOIN users u ON br.user_id = u.id
        WHERE 1=1
    '''
    params = []

    if status_filter != 'all':
        query += ' AND br.status = ?'
        params.append(status_filter)

    if severity_filter != 'all':
        query += ' AND br.severity = ?'
        params.append(severity_filter)

    query += ' ORDER BY br.created_at DESC'

    bugs = db.execute(query, params).fetchall()
    return render_template('bug_list.html', bugs=bugs, status_filter=status_filter, severity_filter=severity_filter)

@bug_reporter.route('/my-bugs')
@login_required
def my_bugs():
    db = get_db()
    bugs = db.execute('''
        SELECT * FROM bug_reports
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (g.user['id'],)).fetchall()

    return render_template('my_bugs.html', bugs=bugs)

def send_bug_notification(bug_id, title, username, severity):
    try:
        smtp_server = os.getenv('SMTP_SERVER', 'localhost')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_user = os.getenv('SMTP_USER', '')
        smtp_pass = os.getenv('SMTP_PASS', '')
        admin_email = os.getenv('ADMIN_EMAIL', 'admin@bottube.ai')

        if not smtp_user:
            return

        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = admin_email
        msg['Subject'] = f'New Bug Report #{bug_id} - {severity.upper()} severity'

        body = f'''
New bug report submitted:

Bug ID: #{bug_id}
Title: {title}
Reported by: {username}
Severity: {severity.upper()}
URL: https://bottube.ai/bug/{bug_id}

Please review and take appropriate action.
'''

        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()

    except Exception as e:
        print(f"Failed to send bug notification: {e}")
