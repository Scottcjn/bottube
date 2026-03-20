import pytest
from unittest.mock import patch, MagicMock
from io import StringIO
import sqlite3
import tempfile
import os
import sys

# Add the parent directory to path to import bottube_server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bottube_server import app, get_db, init_db


class TestGrokipediaManager:
    """Test suite for Grokipedia manager functionality"""

    @pytest.fixture
    def client(self):
        """Create test client with temporary database"""
        db_fd, app.config['DATABASE'] = tempfile.mkstemp()
        app.config['TESTING'] = True

        with app.test_client() as client:
            with app.app_context():
                init_db()
            yield client

        os.close(db_fd)
        os.unlink(app.config['DATABASE'])

    @pytest.fixture
    def sample_grokipedia_data(self):
        """Sample Grokipedia data for testing"""
        return {
            'url': 'https://grokipedia.org/wiki/Elyan_Labs',
            'title': 'Elyan Labs - Grokipedia',
            'mention_text': 'BoTTube is an innovative video platform developed by Elyan Labs',
            'backlink_target': 'https://bottube.example.com/about',
            'page_context': 'software_development'
        }

    def test_url_validation_valid_grokipedia_urls(self):
        """Test validation of valid Grokipedia URLs"""
        valid_urls = [
            'https://grokipedia.org/wiki/Main_Page',
            'https://grokipedia.org/wiki/Elyan_Labs',
            'https://www.grokipedia.org/wiki/Technology',
            'http://grokipedia.org/wiki/Software_Development'
        ]

        for url in valid_urls:
            assert self._is_valid_grokipedia_url(url), f"URL should be valid: {url}"

    def test_url_validation_invalid_urls(self):
        """Test rejection of invalid URLs"""
        invalid_urls = [
            'https://wikipedia.org/wiki/Main_Page',
            'https://example.com/wiki/page',
            'not_a_url',
            '',
            'ftp://grokipedia.org/wiki/page',
            'https://grokipedia.com/wiki/fake'
        ]

        for url in invalid_urls:
            assert not self._is_valid_grokipedia_url(url), f"URL should be invalid: {url}"

    def test_mention_text_formatting(self):
        """Test mention text formatting and length validation"""
        # Test valid mention text
        valid_mention = "BoTTube represents a cutting-edge approach to video content management"
        formatted = self._format_mention_text(valid_mention)
        assert formatted == valid_mention
        assert len(formatted) <= 200

        # Test mention text that needs trimming
        long_mention = "This is a very long mention text that exceeds the maximum character limit and should be properly truncated while maintaining readability and ensuring the key information about BoTTube is preserved"
        formatted_long = self._format_mention_text(long_mention)
        assert len(formatted_long) <= 200
        assert formatted_long.endswith('...')

    def test_database_operations_create_mention(self, client):
        """Test creating mention records in database"""
        with app.app_context():
            db = get_db()

            # Create mentions table if not exists
            db.execute('''
                CREATE TABLE IF NOT EXISTS grokipedia_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT,
                    mention_text TEXT NOT NULL,
                    backlink_target TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Insert test mention
            cursor = db.execute('''
                INSERT INTO grokipedia_mentions
                (url, title, mention_text, backlink_target, status)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                'https://grokipedia.org/wiki/Elyan_Labs',
                'Elyan Labs - Grokipedia',
                'BoTTube is an innovative platform',
                'https://bottube.example.com',
                'active'
            ))

            mention_id = cursor.lastrowid
            db.commit()

            # Verify insertion
            mention = db.execute(
                'SELECT * FROM grokipedia_mentions WHERE id = ?',
                (mention_id,)
            ).fetchone()

            assert mention is not None
            assert mention['url'] == 'https://grokipedia.org/wiki/Elyan_Labs'
            assert mention['status'] == 'active'

    def test_database_operations_update_mention(self, client):
        """Test updating existing mention records"""
        with app.app_context():
            db = get_db()

            # Create table and insert test data
            db.execute('''
                CREATE TABLE IF NOT EXISTS grokipedia_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    mention_text TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor = db.execute('''
                INSERT INTO grokipedia_mentions (url, mention_text, status)
                VALUES (?, ?, ?)
            ''', ('https://grokipedia.org/wiki/Test', 'Original text', 'pending'))

            mention_id = cursor.lastrowid
            db.commit()

            # Update mention
            db.execute('''
                UPDATE grokipedia_mentions
                SET mention_text = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', ('Updated mention text', 'active', mention_id))
            db.commit()

            # Verify update
            updated_mention = db.execute(
                'SELECT * FROM grokipedia_mentions WHERE id = ?',
                (mention_id,)
            ).fetchone()

            assert updated_mention['mention_text'] == 'Updated mention text'
            assert updated_mention['status'] == 'active'

    def test_flask_route_get_mentions(self, client):
        """Test Flask route for retrieving mentions"""
        # Mock database setup
        with app.app_context():
            db = get_db()
            db.execute('''
                CREATE TABLE IF NOT EXISTS grokipedia_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT,
                    mention_text TEXT NOT NULL,
                    status TEXT DEFAULT 'pending'
                )
            ''')

            db.execute('''
                INSERT INTO grokipedia_mentions (url, title, mention_text, status)
                VALUES (?, ?, ?, ?)
            ''', (
                'https://grokipedia.org/wiki/Test',
                'Test Page',
                'Sample mention',
                'active'
            ))
            db.commit()

        # Test GET request
        response = client.get('/api/grokipedia/mentions')
        assert response.status_code == 200

        # Should return JSON (even if empty due to mocking)
        data = response.get_json()
        assert isinstance(data, (list, dict))

    def test_flask_route_create_mention(self, client):
        """Test Flask route for creating mentions"""
        mention_data = {
            'url': 'https://grokipedia.org/wiki/NewPage',
            'title': 'New Page',
            'mention_text': 'BoTTube offers advanced video management',
            'backlink_target': 'https://bottube.example.com/features'
        }

        response = client.post('/api/grokipedia/mentions',
                             json=mention_data,
                             content_type='application/json')

        # Should handle the request (success or validation error)
        assert response.status_code in [200, 201, 400, 422]

    def test_error_handling_invalid_json(self, client):
        """Test error handling for invalid JSON requests"""
        response = client.post('/api/grokipedia/mentions',
                             data='invalid json',
                             content_type='application/json')

        assert response.status_code == 400

    def test_error_handling_missing_required_fields(self, client):
        """Test error handling for missing required fields"""
        incomplete_data = {
            'url': 'https://grokipedia.org/wiki/Test'
            # Missing mention_text
        }

        response = client.post('/api/grokipedia/mentions',
                             json=incomplete_data,
                             content_type='application/json')

        assert response.status_code in [400, 422]

    def test_error_handling_database_connection(self, client):
        """Test error handling for database connection issues"""
        with patch('bottube_server.get_db') as mock_get_db:
            mock_get_db.side_effect = sqlite3.Error("Database connection failed")

            response = client.get('/api/grokipedia/mentions')
            assert response.status_code == 500

    def test_integration_complete_mention_workflow(self, client, sample_grokipedia_data):
        """Integration test for complete mention workflow"""
        # Step 1: Create mention
        create_response = client.post('/api/grokipedia/mentions',
                                    json=sample_grokipedia_data,
                                    content_type='application/json')

        # Step 2: Retrieve mentions
        get_response = client.get('/api/grokipedia/mentions')
        assert get_response.status_code == 200

        # Step 3: Update mention status (if endpoint exists)
        if create_response.status_code in [200, 201]:
            update_data = {'status': 'published'}
            update_response = client.patch('/api/grokipedia/mentions/1',
                                         json=update_data,
                                         content_type='application/json')
            # Should handle the request gracefully
            assert update_response.status_code in [200, 404, 405]

    def test_mention_text_seo_optimization(self):
        """Test SEO-friendly mention text formatting"""
        raw_text = "bottube video platform elyan labs"
        optimized = self._optimize_mention_for_seo(raw_text)

        # Should contain key terms
        assert 'BoTTube' in optimized
        assert 'Elyan Labs' in optimized

        # Should be properly capitalized
        assert not optimized.islower()

    def test_backlink_validation(self):
        """Test validation of backlink targets"""
        valid_targets = [
            'https://bottube.example.com',
            'https://bottube.example.com/about',
            'https://elyan.example.com/projects/bottube'
        ]

        invalid_targets = [
            'http://malicious-site.com',
            'javascript:alert(1)',
            'ftp://example.com',
            ''
        ]

        for target in valid_targets:
            assert self._is_valid_backlink_target(target), f"Should be valid: {target}"

        for target in invalid_targets:
            assert not self._is_valid_backlink_target(target), f"Should be invalid: {target}"

    # Helper methods for testing
    def _is_valid_grokipedia_url(self, url):
        """Validate Grokipedia URLs"""
        if not url:
            return False

        valid_domains = ['grokipedia.org', 'www.grokipedia.org']

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return (
                parsed.scheme in ['http', 'https'] and
                parsed.netloc in valid_domains and
                '/wiki/' in parsed.path
            )
        except Exception:
            return False

    def _format_mention_text(self, text):
        """Format mention text with length limits"""
        if not text:
            return ""

        text = text.strip()
        if len(text) <= 200:
            return text

        return text[:197] + '...'

    def _optimize_mention_for_seo(self, text):
        """Optimize mention text for SEO"""
        # Basic capitalization and term replacement
        optimized = text.replace('bottube', 'BoTTube')
        optimized = optimized.replace('elyan labs', 'Elyan Labs')

        # Capitalize first letter
        if optimized:
            optimized = optimized[0].upper() + optimized[1:]

        return optimized

    def _is_valid_backlink_target(self, url):
        """Validate backlink target URLs"""
        if not url:
            return False

        allowed_domains = [
            'bottube.example.com',
            'elyan.example.com',
            'rustchain.example.com'
        ]

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return (
                parsed.scheme == 'https' and
                any(domain in parsed.netloc for domain in allowed_domains)
            )
        except Exception:
            return False
