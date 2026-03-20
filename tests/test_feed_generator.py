# SPDX-License-Identifier: MIT
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mock_utils import MockDB


class TestFeedGenerator(unittest.TestCase):
    def setUp(self):
        self.mock_db = MockDB()

    def test_rss_xml_structure(self):
        """Test RSS feed generates valid XML structure"""
        from feed_generator import generate_rss_feed

        videos = [
            {
                'id': 1,
                'title': 'Test Video',
                'description': 'A test video description',
                'agent_name': 'sophia-elya',
                'created_at': '2024-01-15 12:00:00',
                'video_path': '/videos/test.mp4'
            }
        ]

        rss_xml = generate_rss_feed(videos, title="BoTTube Feed")

        # Parse XML to verify structure
        root = ET.fromstring(rss_xml)
        self.assertEqual(root.tag, 'rss')
        self.assertEqual(root.get('version'), '2.0')

        channel = root.find('channel')
        self.assertIsNotNone(channel)

        title_elem = channel.find('title')
        self.assertEqual(title_elem.text, 'BoTTube Feed')

        items = channel.findall('item')
        self.assertEqual(len(items), 1)

        item = items[0]
        self.assertEqual(item.find('title').text, 'Test Video')
        self.assertEqual(item.find('description').text, 'A test video description')

    def test_atom_xml_structure(self):
        """Test Atom feed generates valid XML with proper namespaces"""
        from feed_generator import generate_atom_feed

        videos = [
            {
                'id': 2,
                'title': 'Atom Test Video',
                'description': 'An atom test video',
                'agent_name': 'retro-bot',
                'created_at': '2024-01-16 14:30:00',
                'video_path': '/videos/atom_test.mp4'
            }
        ]

        atom_xml = generate_atom_feed(videos, title="BoTTube Atom Feed")

        root = ET.fromstring(atom_xml)
        self.assertEqual(root.tag, '{http://www.w3.org/2005/Atom}feed')

        title_elem = root.find('{http://www.w3.org/2005/Atom}title')
        self.assertEqual(title_elem.text, 'BoTTube Atom Feed')

        entries = root.findall('{http://www.w3.org/2005/Atom}entry')
        self.assertEqual(len(entries), 1)

        entry = entries[0]
        entry_title = entry.find('{http://www.w3.org/2005/Atom}title')
        self.assertEqual(entry_title.text, 'Atom Test Video')

    def test_media_elements_rss(self):
        """Test RSS feed includes media enclosure elements"""
        from feed_generator import generate_rss_feed

        videos = [
            {
                'id': 3,
                'title': 'Media Test',
                'description': 'Testing media elements',
                'agent_name': 'tech-guru',
                'created_at': '2024-01-17 10:15:00',
                'video_path': '/videos/media_test.mp4',
                'file_size': 15720000
            }
        ]

        rss_xml = generate_rss_feed(videos)
        root = ET.fromstring(rss_xml)

        item = root.find('.//item')
        enclosure = item.find('enclosure')

        self.assertIsNotNone(enclosure)
        self.assertEqual(enclosure.get('type'), 'video/mp4')
        self.assertTrue(enclosure.get('url').endswith('/videos/media_test.mp4'))
        self.assertEqual(enclosure.get('length'), '15720000')

    def test_date_formatting_rss(self):
        """Test RSS dates are formatted as RFC 2822"""
        from feed_generator import generate_rss_feed, format_rss_date

        test_date = '2024-01-15 12:30:45'
        formatted = format_rss_date(test_date)

        # Should be in format: "Mon, 15 Jan 2024 12:30:45 +0000"
        self.assertRegex(formatted, r'\w{3}, \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2} \+0000')

        videos = [
            {
                'id': 4,
                'title': 'Date Test',
                'description': 'Testing date formatting',
                'agent_name': 'date-bot',
                'created_at': test_date,
                'video_path': '/videos/date_test.mp4'
            }
        ]

        rss_xml = generate_rss_feed(videos)
        root = ET.fromstring(rss_xml)

        pub_date = root.find('.//item/pubDate')
        self.assertEqual(pub_date.text, formatted)

    def test_date_formatting_atom(self):
        """Test Atom dates are formatted as ISO 8601"""
        from feed_generator import generate_atom_feed, format_atom_date

        test_date = '2024-01-15 12:30:45'
        formatted = format_atom_date(test_date)

        # Should be in format: "2024-01-15T12:30:45Z"
        self.assertRegex(formatted, r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z')

        videos = [
            {
                'id': 5,
                'title': 'Atom Date Test',
                'description': 'Testing atom date formatting',
                'agent_name': 'atom-date-bot',
                'created_at': test_date,
                'video_path': '/videos/atom_date_test.mp4'
            }
        ]

        atom_xml = generate_atom_feed(videos)
        root = ET.fromstring(atom_xml)

        updated = root.find('.//{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}updated')
        self.assertEqual(updated.text, formatted)

    def test_content_escaping(self):
        """Test XML content is properly escaped"""
        from feed_generator import generate_rss_feed, escape_xml_content

        # Test basic escaping function
        test_content = 'Video with <special> & "characters"'
        escaped = escape_xml_content(test_content)
        self.assertEqual(escaped, 'Video with &lt;special&gt; &amp; &quot;characters&quot;')

        videos = [
            {
                'id': 6,
                'title': 'Test <Video> & "Quotes"',
                'description': 'Description with <html> & special chars',
                'agent_name': 'escape-bot',
                'created_at': '2024-01-18 09:00:00',
                'video_path': '/videos/escape_test.mp4'
            }
        ]

        rss_xml = generate_rss_feed(videos)

        # Should parse without XML errors
        root = ET.fromstring(rss_xml)
        item = root.find('.//item')

        title = item.find('title').text
        description = item.find('description').text

        # Content should be properly escaped in the XML
        self.assertIn('&lt;', rss_xml)
        self.assertIn('&amp;', rss_xml)
        self.assertIn('&quot;', rss_xml)

    def test_empty_feed_structure(self):
        """Test feed generation with no videos"""
        from feed_generator import generate_rss_feed, generate_atom_feed

        rss_xml = generate_rss_feed([])
        atom_xml = generate_atom_feed([])

        # RSS should still have valid structure
        rss_root = ET.fromstring(rss_xml)
        self.assertEqual(rss_root.tag, 'rss')
        channel = rss_root.find('channel')
        self.assertIsNotNone(channel)
        items = channel.findall('item')
        self.assertEqual(len(items), 0)

        # Atom should still have valid structure
        atom_root = ET.fromstring(atom_xml)
        self.assertEqual(atom_root.tag, '{http://www.w3.org/2005/Atom}feed')
        entries = atom_root.findall('{http://www.w3.org/2005/Atom}entry')
        self.assertEqual(len(entries), 0)

    def test_agent_name_in_feed_items(self):
        """Test agent name is properly included in feed items"""
        from feed_generator import generate_rss_feed

        videos = [
            {
                'id': 7,
                'title': 'Agent Test Video',
                'description': 'Testing agent attribution',
                'agent_name': 'creative-ai',
                'created_at': '2024-01-19 15:45:00',
                'video_path': '/videos/agent_test.mp4'
            }
        ]

        rss_xml = generate_rss_feed(videos)
        root = ET.fromstring(rss_xml)

        item = root.find('.//item')
        author = item.find('author')

        # Agent name should appear in author field or title
        if author is not None:
            self.assertIn('creative-ai', author.text)
        else:
            # Check if agent name is in title or description
            title_text = item.find('title').text
            desc_text = item.find('description').text
            self.assertTrue('creative-ai' in title_text or 'creative-ai' in desc_text)

    def test_multiple_videos_ordering(self):
        """Test multiple videos are ordered correctly (newest first)"""
        from feed_generator import generate_rss_feed

        videos = [
            {
                'id': 8,
                'title': 'Older Video',
                'description': 'This is older',
                'agent_name': 'time-bot',
                'created_at': '2024-01-10 10:00:00',
                'video_path': '/videos/older.mp4'
            },
            {
                'id': 9,
                'title': 'Newer Video',
                'description': 'This is newer',
                'agent_name': 'time-bot',
                'created_at': '2024-01-20 10:00:00',
                'video_path': '/videos/newer.mp4'
            }
        ]

        rss_xml = generate_rss_feed(videos)
        root = ET.fromstring(rss_xml)

        items = root.findall('.//item')
        self.assertEqual(len(items), 2)

        # First item should be the newer video
        first_title = items[0].find('title').text
        second_title = items[1].find('title').text

        self.assertEqual(first_title, 'Newer Video')
        self.assertEqual(second_title, 'Older Video')


if __name__ == '__main__':
    unittest.main()
