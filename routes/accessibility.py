from flask import Blueprint, request, jsonify, g, session
from datetime import datetime
import sqlite3
from database import get_db

accessibility_bp = Blueprint('accessibility', __name__, url_prefix='/api/accessibility')

@accessibility_bp.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)
        ).fetchone()

@accessibility_bp.route('/report', methods=['POST'])
def report_issue():
    if g.user is None:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON data'}), 400

    issue_type = data.get('type')
    description = data.get('description')
    page_url = data.get('page_url')
    severity = data.get('severity', 'medium')

    if not all([issue_type, description, page_url]):
        return jsonify({'error': 'Missing required fields: type, description, page_url'}), 400

    valid_types = ['contrast', 'screen-reader', 'keyboard', 'focus', 'aria', 'other']
    if issue_type not in valid_types:
        return jsonify({'error': f'Invalid issue type. Must be one of: {", ".join(valid_types)}'}), 400

    valid_severities = ['low', 'medium', 'high', 'critical']
    if severity not in valid_severities:
        return jsonify({'error': f'Invalid severity. Must be one of: {", ".join(valid_severities)}'}), 400

    db = get_db()
    try:
        cursor = db.execute(
            '''INSERT INTO accessibility_reports
               (user_id, issue_type, description, page_url, severity, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (g.user['id'], issue_type, description, page_url, severity, 'pending', datetime.utcnow())
        )
        db.commit()

        report_id = cursor.lastrowid

        return jsonify({
            'message': 'Accessibility report submitted successfully',
            'report_id': report_id,
            'reward_eligible': True
        }), 201

    except sqlite3.Error as e:
        return jsonify({'error': 'Database error occurred'}), 500

@accessibility_bp.route('/reports', methods=['GET'])
def get_reports():
    if g.user is None:
        return jsonify({'error': 'Authentication required'}), 401

    status_filter = request.args.get('status')
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)

    db = get_db()

    base_query = '''
        SELECT ar.*, u.username
        FROM accessibility_reports ar
        JOIN users u ON ar.user_id = u.id
    '''

    params = []
    if status_filter:
        base_query += ' WHERE ar.status = ?'
        params.append(status_filter)

    base_query += ' ORDER BY ar.created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])

    reports = db.execute(base_query, params).fetchall()

    report_list = []
    for report in reports:
        report_list.append({
            'id': report['id'],
            'user_id': report['user_id'],
            'username': report['username'],
            'issue_type': report['issue_type'],
            'description': report['description'],
            'page_url': report['page_url'],
            'severity': report['severity'],
            'status': report['status'],
            'created_at': report['created_at'],
            'resolved_at': report['resolved_at']
        })

    return jsonify({
        'reports': report_list,
        'page': page,
        'per_page': per_page
    })

@accessibility_bp.route('/reports/<int:report_id>/status', methods=['PUT'])
def update_report_status():
    if g.user is None:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({'error': 'Status field required'}), 400

    new_status = data['status']
    valid_statuses = ['pending', 'verified', 'invalid', 'duplicate', 'resolved']

    if new_status not in valid_statuses:
        return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400

    db = get_db()

    update_fields = ['status = ?']
    params = [new_status]

    if new_status == 'resolved':
        update_fields.append('resolved_at = ?')
        params.append(datetime.utcnow())

    params.append(report_id)

    result = db.execute(
        f'UPDATE accessibility_reports SET {", ".join(update_fields)} WHERE id = ?',
        params
    )

    if result.rowcount == 0:
        return jsonify({'error': 'Report not found'}), 404

    db.commit()

    return jsonify({
        'message': f'Report status updated to {new_status}',
        'reward_processed': new_status == 'verified'
    })

@accessibility_bp.route('/stats', methods=['GET'])
def get_accessibility_stats():
    if g.user is None:
        return jsonify({'error': 'Authentication required'}), 401

    db = get_db()

    stats = {}

    # Total reports by status
    status_counts = db.execute('''
        SELECT status, COUNT(*) as count
        FROM accessibility_reports
        GROUP BY status
    ''').fetchall()

    stats['by_status'] = {row['status']: row['count'] for row in status_counts}

    # Reports by type
    type_counts = db.execute('''
        SELECT issue_type, COUNT(*) as count
        FROM accessibility_reports
        GROUP BY issue_type
    ''').fetchall()

    stats['by_type'] = {row['issue_type']: row['count'] for row in type_counts}

    # Reports by severity
    severity_counts = db.execute('''
        SELECT severity, COUNT(*) as count
        FROM accessibility_reports
        GROUP BY severity
    ''').fetchall()

    stats['by_severity'] = {row['severity']: row['count'] for row in severity_counts}

    # Top reporters
    top_reporters = db.execute('''
        SELECT u.username, COUNT(*) as report_count
        FROM accessibility_reports ar
        JOIN users u ON ar.user_id = u.id
        GROUP BY u.id, u.username
        ORDER BY report_count DESC
        LIMIT 10
    ''').fetchall()

    stats['top_reporters'] = [
        {'username': row['username'], 'count': row['report_count']}
        for row in top_reporters
    ]

    return jsonify(stats)
