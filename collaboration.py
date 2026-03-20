from flask import Blueprint, request, jsonify, session, g
import sqlite3
from functools import wraps
import datetime
import uuid
import logging

collaboration = Blueprint('collaboration', __name__)

def get_db():
    """Get database connection"""
    if 'db' not in g:
        g.db = sqlite3.connect('bottube.db')
        g.db.row_factory = sqlite3.Row
    return g.db

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 401
        g.user = user
        return f(*args, **kwargs)
    return decorated_function

def init_collaboration_tables():
    """Initialize collaboration-related database tables"""
    db = get_db()

    # Collaborations table
    db.execute('''
        CREATE TABLE IF NOT EXISTS collaborations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            creator_id INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            project_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deadline DATE,
            budget DECIMAL(10,2),
            FOREIGN KEY (creator_id) REFERENCES users (id)
        )
    ''')

    # Collaboration participants table
    db.execute('''
        CREATE TABLE IF NOT EXISTS collaboration_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collaboration_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'contributor',
            status TEXT DEFAULT 'pending',
            invited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            joined_at TIMESTAMP,
            revenue_share DECIMAL(5,2) DEFAULT 0.00,
            FOREIGN KEY (collaboration_id) REFERENCES collaborations (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Cross-promotion campaigns table
    db.execute('''
        CREATE TABLE IF NOT EXISTS cross_promotions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            creator_id INTEGER NOT NULL,
            target_audience TEXT,
            promotion_type TEXT,
            start_date DATE,
            end_date DATE,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (creator_id) REFERENCES users (id)
        )
    ''')

    # Cross-promotion participants table
    db.execute('''
        CREATE TABLE IF NOT EXISTS promotion_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promotion_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            commitment_type TEXT,
            status TEXT DEFAULT 'invited',
            metrics TEXT,
            joined_at TIMESTAMP,
            FOREIGN KEY (promotion_id) REFERENCES cross_promotions (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    db.commit()

@collaboration.route('/api/collaborations', methods=['POST'])
@login_required
def create_collaboration():
    """Create a new collaboration project"""
    try:
        data = request.get_json()

        if not data or not data.get('title'):
            return jsonify({'error': 'Title is required'}), 400

        collaboration_id = str(uuid.uuid4())
        db = get_db()

        db.execute('''
            INSERT INTO collaborations
            (id, title, description, creator_id, project_type, deadline, budget)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            collaboration_id,
            data['title'],
            data.get('description', ''),
            g.user['id'],
            data.get('project_type', 'general'),
            data.get('deadline'),
            data.get('budget', 0.00)
        ))

        # Add creator as lead participant
        db.execute('''
            INSERT INTO collaboration_participants
            (collaboration_id, user_id, role, status, revenue_share)
            VALUES (?, ?, ?, ?, ?)
        ''', (collaboration_id, g.user['id'], 'lead', 'accepted', data.get('creator_share', 40.00)))

        db.commit()

        return jsonify({
            'success': True,
            'collaboration_id': collaboration_id,
            'message': 'Collaboration created successfully'
        }), 201

    except Exception as e:
        logging.error(f"Error creating collaboration: {e}")
        return jsonify({'error': 'Failed to create collaboration'}), 500

@collaboration.route('/api/collaborations', methods=['GET'])
@login_required
def list_collaborations():
    """List user's collaborations"""
    try:
        db = get_db()

        collaborations = db.execute('''
            SELECT c.*, u.username as creator_name,
                   COUNT(cp.id) as participant_count
            FROM collaborations c
            JOIN users u ON c.creator_id = u.id
            LEFT JOIN collaboration_participants cp ON c.id = cp.collaboration_id
            WHERE c.creator_id = ? OR c.id IN (
                SELECT collaboration_id FROM collaboration_participants
                WHERE user_id = ? AND status = 'accepted'
            )
            GROUP BY c.id
            ORDER BY c.created_at DESC
        ''', (g.user['id'], g.user['id'])).fetchall()

        result = []
        for collab in collaborations:
            result.append({
                'id': collab['id'],
                'title': collab['title'],
                'description': collab['description'],
                'creator_name': collab['creator_name'],
                'status': collab['status'],
                'project_type': collab['project_type'],
                'participant_count': collab['participant_count'],
                'created_at': collab['created_at'],
                'deadline': collab['deadline'],
                'budget': float(collab['budget']) if collab['budget'] else 0.00
            })

        return jsonify({'collaborations': result}), 200

    except Exception as e:
        logging.error(f"Error listing collaborations: {e}")
        return jsonify({'error': 'Failed to fetch collaborations'}), 500

@collaboration.route('/api/collaborations/<collaboration_id>/invite', methods=['POST'])
@login_required
def invite_to_collaboration(collaboration_id):
    """Invite a creator to join collaboration"""
    try:
        data = request.get_json()

        if not data or not data.get('username'):
            return jsonify({'error': 'Username is required'}), 400

        db = get_db()

        # Check if collaboration exists and user is the creator
        collab = db.execute('''
            SELECT * FROM collaborations WHERE id = ? AND creator_id = ?
        ''', (collaboration_id, g.user['id'])).fetchone()

        if not collab:
            return jsonify({'error': 'Collaboration not found or access denied'}), 404

        # Find invited user
        invited_user = db.execute('''
            SELECT * FROM users WHERE username = ?
        ''', (data['username'],)).fetchone()

        if not invited_user:
            return jsonify({'error': 'User not found'}), 404

        # Check if already invited
        existing = db.execute('''
            SELECT * FROM collaboration_participants
            WHERE collaboration_id = ? AND user_id = ?
        ''', (collaboration_id, invited_user['id'])).fetchone()

        if existing:
            return jsonify({'error': 'User already invited'}), 400

        # Add participant
        db.execute('''
            INSERT INTO collaboration_participants
            (collaboration_id, user_id, role, revenue_share)
            VALUES (?, ?, ?, ?)
        ''', (
            collaboration_id,
            invited_user['id'],
            data.get('role', 'contributor'),
            data.get('revenue_share', 0.00)
        ))

        db.commit()

        return jsonify({
            'success': True,
            'message': f'Invitation sent to {data["username"]}'
        }), 200

    except Exception as e:
        logging.error(f"Error inviting to collaboration: {e}")
        return jsonify({'error': 'Failed to send invitation'}), 500

@collaboration.route('/api/collaborations/<collaboration_id>/respond', methods=['POST'])
@login_required
def respond_to_invitation(collaboration_id):
    """Accept or decline collaboration invitation"""
    try:
        data = request.get_json()

        if not data or data.get('response') not in ['accept', 'decline']:
            return jsonify({'error': 'Valid response required (accept/decline)'}), 400

        db = get_db()

        # Check if invitation exists
        invitation = db.execute('''
            SELECT * FROM collaboration_participants
            WHERE collaboration_id = ? AND user_id = ? AND status = 'pending'
        ''', (collaboration_id, g.user['id'])).fetchone()

        if not invitation:
            return jsonify({'error': 'Invitation not found'}), 404

        # Update status
        new_status = 'accepted' if data['response'] == 'accept' else 'declined'
        joined_at = datetime.datetime.now().isoformat() if new_status == 'accepted' else None

        db.execute('''
            UPDATE collaboration_participants
            SET status = ?, joined_at = ?
            WHERE collaboration_id = ? AND user_id = ?
        ''', (new_status, joined_at, collaboration_id, g.user['id']))

        db.commit()

        return jsonify({
            'success': True,
            'message': f'Invitation {data["response"]}ed'
        }), 200

    except Exception as e:
        logging.error(f"Error responding to invitation: {e}")
        return jsonify({'error': 'Failed to respond to invitation'}), 500

@collaboration.route('/api/collaborations/<collaboration_id>', methods=['GET'])
@login_required
def get_collaboration_details(collaboration_id):
    """Get detailed collaboration information"""
    try:
        db = get_db()

        # Get collaboration info
        collab = db.execute('''
            SELECT c.*, u.username as creator_name
            FROM collaborations c
            JOIN users u ON c.creator_id = u.id
            WHERE c.id = ?
        ''', (collaboration_id,)).fetchone()

        if not collab:
            return jsonify({'error': 'Collaboration not found'}), 404

        # Check if user has access
        participant = db.execute('''
            SELECT * FROM collaboration_participants
            WHERE collaboration_id = ? AND user_id = ?
        ''', (collaboration_id, g.user['id'])).fetchone()

        if not participant and collab['creator_id'] != g.user['id']:
            return jsonify({'error': 'Access denied'}), 403

        # Get all participants
        participants = db.execute('''
            SELECT cp.*, u.username, u.email
            FROM collaboration_participants cp
            JOIN users u ON cp.user_id = u.id
            WHERE cp.collaboration_id = ?
        ''', (collaboration_id,)).fetchall()

        result = {
            'id': collab['id'],
            'title': collab['title'],
            'description': collab['description'],
            'creator_name': collab['creator_name'],
            'status': collab['status'],
            'project_type': collab['project_type'],
            'created_at': collab['created_at'],
            'deadline': collab['deadline'],
            'budget': float(collab['budget']) if collab['budget'] else 0.00,
            'participants': []
        }

        for p in participants:
            result['participants'].append({
                'username': p['username'],
                'role': p['role'],
                'status': p['status'],
                'revenue_share': float(p['revenue_share']) if p['revenue_share'] else 0.00,
                'joined_at': p['joined_at']
            })

        return jsonify(result), 200

    except Exception as e:
        logging.error(f"Error getting collaboration details: {e}")
        return jsonify({'error': 'Failed to fetch collaboration details'}), 500

@collaboration.route('/api/cross-promotions', methods=['POST'])
@login_required
def create_cross_promotion():
    """Create a new cross-promotion campaign"""
    try:
        data = request.get_json()

        if not data or not data.get('title'):
            return jsonify({'error': 'Title is required'}), 400

        promotion_id = str(uuid.uuid4())
        db = get_db()

        db.execute('''
            INSERT INTO cross_promotions
            (id, title, description, creator_id, target_audience, promotion_type, start_date, end_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            promotion_id,
            data['title'],
            data.get('description', ''),
            g.user['id'],
            data.get('target_audience', ''),
            data.get('promotion_type', 'content_swap'),
            data.get('start_date'),
            data.get('end_date')
        ))

        db.commit()

        return jsonify({
            'success': True,
            'promotion_id': promotion_id,
            'message': 'Cross-promotion campaign created successfully'
        }), 201

    except Exception as e:
        logging.error(f"Error creating cross-promotion: {e}")
        return jsonify({'error': 'Failed to create cross-promotion campaign'}), 500

@collaboration.route('/api/cross-promotions', methods=['GET'])
@login_required
def list_cross_promotions():
    """List user's cross-promotion campaigns"""
    try:
        db = get_db()

        promotions = db.execute('''
            SELECT cp.*, u.username as creator_name,
                   COUNT(pp.id) as participant_count
            FROM cross_promotions cp
            JOIN users u ON cp.creator_id = u.id
            LEFT JOIN promotion_participants pp ON cp.id = pp.promotion_id
            WHERE cp.creator_id = ? OR cp.id IN (
                SELECT promotion_id FROM promotion_participants
                WHERE user_id = ?
            )
            GROUP BY cp.id
            ORDER BY cp.created_at DESC
        ''', (g.user['id'], g.user['id'])).fetchall()

        result = []
        for promo in promotions:
            result.append({
                'id': promo['id'],
                'title': promo['title'],
                'description': promo['description'],
                'creator_name': promo['creator_name'],
                'status': promo['status'],
                'promotion_type': promo['promotion_type'],
                'participant_count': promo['participant_count'],
                'start_date': promo['start_date'],
                'end_date': promo['end_date']
            })

        return jsonify({'promotions': result}), 200

    except Exception as e:
        logging.error(f"Error listing cross-promotions: {e}")
        return jsonify({'error': 'Failed to fetch cross-promotions'}), 500

@collaboration.route('/api/revenue/splits/<collaboration_id>', methods=['GET'])
@login_required
def get_revenue_splits(collaboration_id):
    """Get revenue sharing configuration for collaboration"""
    try:
        db = get_db()

        # Verify access
        participant = db.execute('''
            SELECT * FROM collaboration_participants
            WHERE collaboration_id = ? AND user_id = ?
        ''', (collaboration_id, g.user['id'])).fetchone()

        if not participant:
            return jsonify({'error': 'Access denied'}), 403

        splits = db.execute('''
            SELECT cp.user_id, cp.revenue_share, cp.role, u.username
            FROM collaboration_participants cp
            JOIN users u ON cp.user_id = u.id
            WHERE cp.collaboration_id = ? AND cp.status = 'accepted'
        ''', (collaboration_id,)).fetchall()

        result = []
        total_share = 0.0

        for split in splits:
            share = float(split['revenue_share']) if split['revenue_share'] else 0.0
            total_share += share
            result.append({
                'username': split['username'],
                'role': split['role'],
                'revenue_share': share
            })

        return jsonify({
            'splits': result,
            'total_allocated': total_share,
            'remaining': max(0.0, 100.0 - total_share)
        }), 200

    except Exception as e:
        logging.error(f"Error getting revenue splits: {e}")
        return jsonify({'error': 'Failed to fetch revenue splits'}), 500

@collaboration.route('/api/revenue/splits/<collaboration_id>', methods=['PUT'])
@login_required
def update_revenue_splits(collaboration_id):
    """Update revenue sharing configuration"""
    try:
        data = request.get_json()

        if not data or not data.get('splits'):
            return jsonify({'error': 'Revenue splits data required'}), 400

        db = get_db()

        # Check if user is collaboration creator
        collab = db.execute('''
            SELECT * FROM collaborations WHERE id = ? AND creator_id = ?
        ''', (collaboration_id, g.user['id'])).fetchone()

        if not collab:
            return jsonify({'error': 'Access denied - creator only'}), 403

        # Validate splits total to 100%
        total_share = sum(float(split.get('revenue_share', 0)) for split in data['splits'])
        if total_share > 100.0:
            return jsonify({'error': 'Total revenue share cannot exceed 100%'}), 400

        # Update splits
        for split in data['splits']:
            db.execute('''
                UPDATE collaboration_participants
                SET revenue_share = ?
                WHERE collaboration_id = ? AND user_id = (
                    SELECT id FROM users WHERE username = ?
                )
            ''', (split['revenue_share'], collaboration_id, split['username']))

        db.commit()

        return jsonify({
            'success': True,
            'message': 'Revenue splits updated successfully'
        }), 200

    except Exception as e:
        logging.error(f"Error updating revenue splits: {e}")
        return jsonify({'error': 'Failed to update revenue splits'}), 500

# Initialize tables when module is loaded
try:
    init_collaboration_tables()
except Exception as e:
    logging.error(f"Error initializing collaboration tables: {e}")
