import sqlite3
import requests
from urllib.parse import urlparse
from flask import g, session, request, jsonify, render_template_string
from functools import wraps
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('bottube.db')
        g.db.row_factory = sqlite3.Row
    return g.db

def init_grokipedia_db():
    """Initialize grokipedia tables in the database"""
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS grokipedia_backlinks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url TEXT NOT NULL,
            target_url TEXT NOT NULL,
            anchor_text TEXT,
            status TEXT DEFAULT 'active',
            last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            check_count INTEGER DEFAULT 0,
            response_code INTEGER,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS blog_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT,
            mention_type TEXT NOT NULL,
            content TEXT NOT NULL,
            url TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        );

        CREATE INDEX IF NOT EXISTS idx_backlinks_url ON grokipedia_backlinks(target_url);
        CREATE INDEX IF NOT EXISTS idx_mentions_post ON blog_mentions(post_id);
    ''')
    db.commit()

class GrokipediaManager:
    def __init__(self):
        self.grokipedia_domains = ['grokipedia.com', 'www.grokipedia.com']
        self.user_agent = 'BoTTube-LinkChecker/1.0'

    def validate_grokipedia_url(self, url):
        """Validate if URL is a proper Grokipedia reference"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return domain in self.grokipedia_domains and parsed.path
        except Exception:
            return False

    def check_link_health(self, url):
        """Check if a backlink is still active and accessible"""
        try:
            headers = {'User-Agent': self.user_agent}
            response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
            return {
                'status_code': response.status_code,
                'accessible': response.status_code == 200,
                'final_url': response.url,
                'content_length': len(response.content) if response.status_code == 200 else 0
            }
        except requests.RequestException as e:
            logger.warning(f"Link check failed for {url}: {str(e)}")
            return {
                'status_code': 0,
                'accessible': False,
                'error': str(e)
            }

    def add_backlink_record(self, source_url, target_url, anchor_text=None, notes=None):
        """Add a new backlink record to database"""
        if not self.validate_grokipedia_url(target_url):
            raise ValueError("Invalid Grokipedia URL format")

        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO grokipedia_backlinks
            (source_url, target_url, anchor_text, notes)
            VALUES (?, ?, ?, ?)
        ''', (source_url, target_url, anchor_text, notes))

        backlink_id = cursor.lastrowid
        db.commit()

        # Perform initial health check
        health_result = self.check_link_health(target_url)
        self.update_link_health(backlink_id, health_result)

        return backlink_id

    def update_link_health(self, backlink_id, health_result):
        """Update backlink health status in database"""
        db = get_db()
        status = 'active' if health_result.get('accessible', False) else 'broken'
        response_code = health_result.get('status_code', 0)

        db.execute('''
            UPDATE grokipedia_backlinks
            SET status = ?, response_code = ?, last_checked = CURRENT_TIMESTAMP,
                check_count = check_count + 1
            WHERE id = ?
        ''', (status, response_code, backlink_id))
        db.commit()

    def get_backlinks_report(self, days_back=30):
        """Generate backlinks health report"""
        db = get_db()
        cutoff_date = datetime.now() - timedelta(days=days_back)

        cursor = db.execute('''
            SELECT * FROM grokipedia_backlinks
            WHERE last_checked >= ?
            ORDER BY last_checked DESC
        ''', (cutoff_date.isoformat(),))

        backlinks = cursor.fetchall()

        stats = {
            'total': len(backlinks),
            'active': sum(1 for b in backlinks if b['status'] == 'active'),
            'broken': sum(1 for b in backlinks if b['status'] == 'broken'),
            'needs_check': sum(1 for b in backlinks if
                             datetime.fromisoformat(b['last_checked']) < datetime.now() - timedelta(days=7))
        }

        return {'backlinks': backlinks, 'stats': stats}

    def add_blog_mention(self, post_id, mention_type, content, url=None):
        """Add Grokipedia mention to blog post record"""
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO blog_mentions (post_id, mention_type, content, url)
            VALUES (?, ?, ?, ?)
        ''', (post_id, mention_type, content, url))

        mention_id = cursor.lastrowid
        db.commit()
        return mention_id

    def get_post_mentions(self, post_id):
        """Get all Grokipedia mentions for a specific post"""
        db = get_db()
        cursor = db.execute('''
            SELECT * FROM blog_mentions
            WHERE post_id = ? AND status = 'active'
            ORDER BY added_date DESC
        ''', (post_id,))
        return cursor.fetchall()

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id') or not g.user.get('is_admin'):
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def setup_grokipedia_routes(app):
    grok_manager = GrokipediaManager()

    @app.route('/admin/grokipedia', methods=['GET'])
    @require_admin
    def grokipedia_dashboard():
        """Admin dashboard for managing Grokipedia references"""
        report = grok_manager.get_backlinks_report()

        dashboard_html = '''
        <h2>Grokipedia Link Management</h2>
        <div class="stats-panel">
            <h3>Link Health Summary</h3>
            <p>Total Links: {{ stats.total }}</p>
            <p>Active: {{ stats.active }}</p>
            <p>Broken: {{ stats.broken }}</p>
            <p>Need Check: {{ stats.needs_check }}</p>
        </div>

        <div class="add-link-form">
            <h3>Add New Backlink</h3>
            <form id="addLinkForm">
                <input type="text" name="source_url" placeholder="Source URL" required>
                <input type="text" name="target_url" placeholder="Grokipedia URL" required>
                <input type="text" name="anchor_text" placeholder="Anchor text">
                <button type="submit">Add Link</button>
            </form>
        </div>

        <div class="backlinks-list">
            <h3>Recent Backlinks</h3>
            {% for link in backlinks %}
            <div class="link-item status-{{ link.status }}">
                <strong>{{ link.source_url }}</strong> → {{ link.target_url }}
                <span class="status">{{ link.status }} ({{ link.response_code }})</span>
                <small>Last checked: {{ link.last_checked }}</small>
            </div>
            {% endfor %}
        </div>
        '''

        return render_template_string(dashboard_html, **report)

    @app.route('/api/grokipedia/backlinks', methods=['POST'])
    @require_admin
    def add_backlink():
        """API endpoint to add new backlink"""
        data = request.get_json()
        source_url = data.get('source_url')
        target_url = data.get('target_url')
        anchor_text = data.get('anchor_text', '')
        notes = data.get('notes', '')

        if not source_url or not target_url:
            return jsonify({'error': 'Source and target URLs required'}), 400

        try:
            backlink_id = grok_manager.add_backlink_record(
                source_url, target_url, anchor_text, notes
            )
            return jsonify({
                'success': True,
                'backlink_id': backlink_id,
                'message': 'Backlink added successfully'
            })
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Failed to add backlink: {str(e)}")
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/grokipedia/mentions', methods=['POST'])
    @require_admin
    def add_mention():
        """API endpoint to add Grokipedia mention to blog post"""
        data = request.get_json()
        post_id = data.get('post_id')
        mention_type = data.get('type', 'reference')
        content = data.get('content')
        url = data.get('url')

        if not post_id or not content:
            return jsonify({'error': 'Post ID and content required'}), 400

        try:
            mention_id = grok_manager.add_blog_mention(
                post_id, mention_type, content, url
            )
            return jsonify({
                'success': True,
                'mention_id': mention_id,
                'message': 'Mention added successfully'
            })
        except Exception as e:
            logger.error(f"Failed to add mention: {str(e)}")
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/grokipedia/health-check', methods=['POST'])
    @require_admin
    def run_health_check():
        """Run health check on all or specific backlinks"""
        data = request.get_json() or {}
        backlink_id = data.get('backlink_id')

        try:
            db = get_db()
            if backlink_id:
                cursor = db.execute(
                    'SELECT * FROM grokipedia_backlinks WHERE id = ?',
                    (backlink_id,)
                )
                backlinks = [cursor.fetchone()]
            else:
                cursor = db.execute('SELECT * FROM grokipedia_backlinks')
                backlinks = cursor.fetchall()

            checked_count = 0
            broken_count = 0

            for link in backlinks:
                if link:
                    health_result = grok_manager.check_link_health(link['target_url'])
                    grok_manager.update_link_health(link['id'], health_result)
                    checked_count += 1
                    if not health_result.get('accessible', False):
                        broken_count += 1

            return jsonify({
                'success': True,
                'checked': checked_count,
                'broken': broken_count,
                'message': f'Checked {checked_count} links, found {broken_count} broken'
            })

        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return jsonify({'error': 'Health check failed'}), 500

    # Initialize database tables
    with app.app_context():
        init_grokipedia_db()
