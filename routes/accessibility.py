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
            'message': 'Accessibility issue reported successfully',
            'report_id': report_id
        }), 201

    except sqlite3.Error as e:
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@accessibility_bp.route('/reports', methods=['GET'])
def get_reports():
    if g.user is None:
        return jsonify({'error': 'Authentication required'}), 401

    status = request.args.get('status', 'all')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page

    db = get_db()
    try:
        # Build query based on filters
        where_clause = ''
        params = []

        if status != 'all':
            where_clause = 'WHERE status = ?'
            params.append(status)

        # Get total count
        count_query = f'SELECT COUNT(*) FROM accessibility_reports {where_clause}'
        total = db.execute(count_query, params).fetchone()[0]

        # Get reports with pagination
        reports_query = f'''
            SELECT ar.*, u.username
            FROM accessibility_reports ar
            JOIN users u ON ar.user_id = u.id
            {where_clause}
            ORDER BY ar.created_at DESC
            LIMIT ? OFFSET ?
        '''
        params.extend([per_page, offset])
        reports = db.execute(reports_query, params).fetchall()

        return jsonify({
            'reports': [dict(report) for report in reports],
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        })

    except sqlite3.Error as e:
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@accessibility_bp.route('/reports/<int:report_id>', methods=['GET'])
def get_report(report_id):
    if g.user is None:
        return jsonify({'error': 'Authentication required'}), 401

    db = get_db()
    try:
        report = db.execute(
            '''SELECT ar.*, u.username
               FROM accessibility_reports ar
               JOIN users u ON ar.user_id = u.id
               WHERE ar.id = ?''',
            (report_id,)
        ).fetchone()

        if not report:
            return jsonify({'error': 'Report not found'}), 404

        return jsonify(dict(report))

    except sqlite3.Error as e:
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@accessibility_bp.route('/reports/<int:report_id>/status', methods=['PATCH'])
def update_report_status(report_id):
    if g.user is None:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({'error': 'Status is required'}), 400

    new_status = data['status']
    valid_statuses = ['pending', 'in_progress', 'resolved', 'dismissed']
    if new_status not in valid_statuses:
        return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400

    db = get_db()
    try:
        # Check if report exists
        report = db.execute(
            'SELECT id FROM accessibility_reports WHERE id = ?',
            (report_id,)
        ).fetchone()

        if not report:
            return jsonify({'error': 'Report not found'}), 404

        # Update status
        db.execute(
            'UPDATE accessibility_reports SET status = ?, updated_at = ? WHERE id = ?',
            (new_status, datetime.utcnow(), report_id)
        )
        db.commit()

        return jsonify({'message': 'Report status updated successfully'})

    except sqlite3.Error as e:
        return jsonify({'error': f'Database error: {str(e)}'}), 500
