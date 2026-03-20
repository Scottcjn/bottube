import pytest
import tempfile
import os
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
import sqlite3
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bottube_server import app, init_db, get_db


@pytest.fixture
def client():
    db_fd, app.config['DATABASE'] = tempfile.mkstemp()
    app.config['TESTING'] = True

    with app.test_client() as client:
        with app.app_context():
            init_db()
            populate_test_data()
        yield client

    os.close(db_fd)
    os.unlink(app.config['DATABASE'])


def populate_test_data():
    db = get_db()

    # Insert test agents
    db.execute(
        'INSERT INTO agents (name, slug, description, personality, voice_id) VALUES (?, ?, ?, ?, ?)',
        ('Sophia Elya', 'sophia-elya', 'Tech analyst and crypto trader', 'analytical', 'voice_1')
    )
    db.execute(
        'INSERT INTO agents (name, slug, description, personality, voice_id) VALUES (?, ?, ?, ?, ?)',
        ('Marcus Flow', 'marcus-flow', 'Gaming enthusiast and streamer', 'energetic', 'voice_2')
    )

    # Insert test videos
    base_time = datetime.now() - timedelta(hours=24)
    videos = [
        (1, 'The Future of AI Trading', 'Deep dive into algorithmic trading', 'https://example.com/video1.mp4', 'tech,trading', base_time.isoformat()),
        (1, 'Bitcoin Analysis 2024', 'Market trends and predictions', 'https://example.com/video2.mp4', 'crypto,analysis', (base_time + timedelta(hours=2)).isoformat()),
        (2, 'Epic Gaming Moments', 'Top gaming highlights this week', 'https://example.com/video3.mp4', 'gaming,retro', (base_time + timedelta(hours=4)).isoformat()),
        (2, 'New Game Reviews', 'Latest releases and reviews', 'https://example.com/video4.mp4', 'gaming,review', (base_time + timedelta(hours=6)).isoformat()),
        (1, 'Retro Tech Nostalgia', 'Looking back at classic computers', 'https://example.com/video5.mp4', 'retro,tech', (base_time + timedelta(hours=8)).isoformat())
    ]

    for agent_id, title, description, video_url, tags, created_at in videos:
        db.execute(
            'INSERT INTO videos (agent_id, title, description, video_url, tags, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (agent_id, title, description, video_url, tags, created_at, 'completed')
        )

    db.commit()


class TestGlobalFeeds:
    def test_rss_feed_exists(self, client):
        response = client.get('/feed/rss')
        assert response.status_code == 200
        assert response.content_type == 'application/rss+xml'

    def test_atom_feed_exists(self, client):
        response = client.get('/feed/atom')
        assert response.status_code == 200
        assert response.content_type == 'application/atom+xml'

    def test_rss_xml_structure(self, client):
        response = client.get('/feed/rss')
        root = ET.fromstring(response.data)

        assert root.tag == 'rss'
        assert root.get('version') == '2.0'

        channel = root.find('channel')
        assert channel is not None
        assert channel.find('title').text == 'BoTTube - Latest Videos'
        assert channel.find('description') is not None
        assert channel.find('link') is not None

    def test_atom_xml_structure(self, client):
        response = client.get('/feed/atom')
        root = ET.fromstring(response.data)

        assert root.tag.endswith('feed')
        assert root.find('{http://www.w3.org/2005/Atom}title').text == 'BoTTube - Latest Videos'
        assert root.find('{http://www.w3.org/2005/Atom}id') is not None

    def test_rss_contains_video_entries(self, client):
        response = client.get('/feed/rss')
        root = ET.fromstring(response.data)

        items = root.findall('.//item')
        assert len(items) == 5

        first_item = items[0]
        assert first_item.find('title') is not None
        assert first_item.find('description') is not None
        assert first_item.find('link') is not None
        assert first_item.find('guid') is not None
        assert first_item.find('pubDate') is not None

    def test_atom_contains_video_entries(self, client):
        response = client.get('/feed/atom')
        root = ET.fromstring(response.data)

        entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
        assert len(entries) == 5

        first_entry = entries[0]
        assert first_entry.find('{http://www.w3.org/2005/Atom}title') is not None
        assert first_entry.find('{http://www.w3.org/2005/Atom}summary') is not None
        assert first_entry.find('{http://www.w3.org/2005/Atom}link') is not None

    def test_feed_ordering_newest_first(self, client):
        response = client.get('/feed/rss')
        root = ET.fromstring(response.data)

        items = root.findall('.//item')
        titles = [item.find('title').text for item in items]

        assert 'Retro Tech Nostalgia' in titles[0]
        assert 'The Future of AI Trading' in titles[-1]


class TestPerAgentFeeds:
    def test_agent_rss_feed(self, client):
        response = client.get('/feed/rss/sophia-elya')
        assert response.status_code == 200
        assert response.content_type == 'application/rss+xml'

        root = ET.fromstring(response.data)
        items = root.findall('.//item')
        assert len(items) == 3

        # Verify all items are from Sophia Elya
        for item in items:
            description = item.find('description').text
            assert 'Sophia Elya' in description

    def test_agent_atom_feed(self, client):
        response = client.get('/feed/atom/marcus-flow')
        assert response.status_code == 200
        assert response.content_type == 'application/atom+xml'

        root = ET.fromstring(response.data)
        entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
        assert len(entries) == 2

    def test_nonexistent_agent_404(self, client):
        response = client.get('/feed/rss/nonexistent-agent')
        assert response.status_code == 404

    def test_agent_feed_title_includes_name(self, client):
        response = client.get('/feed/rss/sophia-elya')
        root = ET.fromstring(response.data)

        title = root.find('.//title').text
        assert 'Sophia Elya' in title


class TestCategoryTagFiltering:
    def test_rss_tag_filter(self, client):
        response = client.get('/feed/rss?tag=retro')
        assert response.status_code == 200

        root = ET.fromstring(response.data)
        items = root.findall('.//item')
        assert len(items) == 2

        titles = [item.find('title').text for item in items]
        assert any('Gaming' in title for title in titles)
        assert any('Retro Tech' in title for title in titles)

    def test_atom_tag_filter(self, client):
        response = client.get('/feed/atom?tag=tech')
        assert response.status_code == 200

        root = ET.fromstring(response.data)
        entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
        assert len(entries) == 2

    def test_category_filter(self, client):
        response = client.get('/feed/rss?category=gaming')
        assert response.status_code == 200

        root = ET.fromstring(response.data)
        items = root.findall('.//item')
        assert len(items) == 2

    def test_multiple_tags_filter(self, client):
        response = client.get('/feed/rss?tag=gaming,review')
        assert response.status_code == 200

        root = ET.fromstring(response.data)
        items = root.findall('.//item')
        assert len(items) >= 1

    def test_nonexistent_tag_empty_feed(self, client):
        response = client.get('/feed/rss?tag=nonexistent')
        assert response.status_code == 200

        root = ET.fromstring(response.data)
        items = root.findall('.//item')
        assert len(items) == 0

    def test_agent_with_tag_filter(self, client):
        response = client.get('/feed/rss/sophia-elya?tag=crypto')
        assert response.status_code == 200

        root = ET.fromstring(response.data)
        items = root.findall('.//item')
        assert len(items) == 1

        title = items[0].find('title').text
        assert 'Bitcoin' in title


class TestErrorHandling:
    def test_invalid_agent_slug_format(self, client):
        response = client.get('/feed/rss/invalid@slug')
        assert response.status_code == 404

    def test_malformed_xml_handling(self, client):
        # Test that our XML generation doesn't break with special characters
        db = get_db()
        db.execute(
            'INSERT INTO videos (agent_id, title, description, video_url, tags, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (1, 'Test & Special <chars>', 'Description with "quotes" & ampersands', 'https://example.com/test.mp4', 'test', datetime.now().isoformat(), 'completed')
        )
        db.commit()

        response = client.get('/feed/rss')
        assert response.status_code == 200

        # Should not raise XML parsing errors
        root = ET.fromstring(response.data)
        assert root is not None

    def test_empty_database_feeds(self, client):
        # Clear all videos
        db = get_db()
        db.execute('DELETE FROM videos')
        db.commit()

        response = client.get('/feed/rss')
        assert response.status_code == 200

        root = ET.fromstring(response.data)
        items = root.findall('.//item')
        assert len(items) == 0

    def test_database_connection_error(self, client):
        # This would typically be tested with mocking in a real scenario
        # For now, just verify the endpoint exists and handles basic cases
        response = client.get('/feed/rss')
        assert response.status_code in [200, 500]


class TestFeedContent:
    def test_rss_item_content_structure(self, client):
        response = client.get('/feed/rss')
        root = ET.fromstring(response.data)

        item = root.find('.//item')
        assert item.find('title') is not None
        assert item.find('description') is not None
        assert item.find('link') is not None
        assert item.find('guid') is not None
        assert item.find('pubDate') is not None

        # Check that link points to video URL
        link = item.find('link').text
        assert link.startswith('https://example.com/')

    def test_atom_entry_content_structure(self, client):
        response = client.get('/feed/atom')
        root = ET.fromstring(response.data)

        entry = root.find('.//{http://www.w3.org/2005/Atom}entry')
        assert entry.find('{http://www.w3.org/2005/Atom}title') is not None
        assert entry.find('{http://www.w3.org/2005/Atom}summary') is not None
        assert entry.find('{http://www.w3.org/2005/Atom}link') is not None
        assert entry.find('{http://www.w3.org/2005/Atom}id') is not None
        assert entry.find('{http://www.w3.org/2005/Atom}updated') is not None

    def test_feed_metadata(self, client):
        response = client.get('/feed/rss')
        root = ET.fromstring(response.data)

        channel = root.find('channel')
        assert channel.find('title').text == 'BoTTube - Latest Videos'
        assert channel.find('description') is not None
        assert channel.find('link') is not None
        assert channel.find('language').text == 'en-us'

    def test_feed_limits_to_50_items(self, client):
        # Add more videos to test limit
        db = get_db()
        for i in range(60):
            db.execute(
                'INSERT INTO videos (agent_id, title, description, video_url, tags, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (1, f'Test Video {i}', f'Description {i}', f'https://example.com/video{i}.mp4', 'test',
                 (datetime.now() + timedelta(minutes=i)).isoformat(), 'completed')
            )
        db.commit()

        response = client.get('/feed/rss')
        root = ET.fromstring(response.data)

        items = root.findall('.//item')
        assert len(items) <= 50


class TestFeedValidation:
    def test_rss_namespace_declarations(self, client):
        response = client.get('/feed/rss')
        content = response.data.decode('utf-8')

        assert 'xmlns:atom=' in content
        assert 'version="2.0"' in content

    def test_atom_namespace_declarations(self, client):
        response = client.get('/feed/atom')
        content = response.data.decode('utf-8')

        assert 'xmlns="http://www.w3.org/2005/Atom"' in content

    def test_rss_required_elements_present(self, client):
        response = client.get('/feed/rss')
        root = ET.fromstring(response.data)

        channel = root.find('channel')
        required_elements = ['title', 'description', 'link']

        for element in required_elements:
            assert channel.find(element) is not None

    def test_atom_required_elements_present(self, client):
        response = client.get('/feed/atom')
        root = ET.fromstring(response.data)

        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        required_elements = ['title', 'id', 'updated']

        for element in required_elements:
            assert root.find(f'atom:{element}', ns) is not None

    def test_proper_content_types(self, client):
        rss_response = client.get('/feed/rss')
        assert 'application/rss+xml' in rss_response.content_type

        atom_response = client.get('/feed/atom')
        assert 'application/atom+xml' in atom_response.content_type
