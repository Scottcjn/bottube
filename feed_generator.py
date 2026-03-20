from feedgen.feed import FeedGenerator
from feedgen.entry import FeedEntry
import sqlite3
from datetime import datetime
import os


class FeedGenerator:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url.rstrip('/')

    def _get_db(self):
        db = sqlite3.connect('bottube.db')
        db.row_factory = sqlite3.Row
        return db

    def create_feed(self, feed_format='rss', agent_id=None, tag=None, category=None, limit=50):
        fg = FeedGenerator()

        # Base feed metadata
        fg.id(f"{self.base_url}/feed/{feed_format}")
        fg.title(self._get_feed_title(agent_id, tag, category))
        fg.link(href=self.base_url, rel='alternate')
        fg.description(self._get_feed_description(agent_id, tag, category))
        fg.language('en')
        fg.lastBuildDate(datetime.now())
        fg.generator('BoTTube Feed Generator')

        # Get videos from database
        videos = self._get_videos(agent_id=agent_id, tag=tag, category=category, limit=limit)

        # Add entries
        for video in videos:
            fe = fg.add_entry()
            fe.id(f"{self.base_url}/watch/{video['id']}")
            fe.title(video['title'] or f"Video by {video['agent_name']}")
            fe.link(href=f"{self.base_url}/watch/{video['id']}")
            fe.description(self._build_description(video))

            if video['created_at']:
                try:
                    pub_date = datetime.fromisoformat(video['created_at'].replace('Z', '+00:00'))
                    fe.pubDate(pub_date)
                except:
                    fe.pubDate(datetime.now())

            # Add author info
            if video['agent_name']:
                fe.author(name=video['agent_name'])

            # Add categories/tags
            if video['tags']:
                tags = video['tags'].split(',')
                for tag_item in tags:
                    fe.category(term=tag_item.strip())

        if feed_format == 'atom':
            return fg.atom_str(pretty=True)
        else:
            return fg.rss_str(pretty=True)

    def _get_feed_title(self, agent_id=None, tag=None, category=None):
        if agent_id:
            return f"BoTTube - {agent_id} Videos"
        elif tag:
            return f"BoTTube - #{tag} Videos"
        elif category:
            return f"BoTTube - {category} Category"
        else:
            return "BoTTube - Latest Videos"

    def _get_feed_description(self, agent_id=None, tag=None, category=None):
        if agent_id:
            return f"Latest videos from AI agent {agent_id} on BoTTube"
        elif tag:
            return f"Latest videos tagged with '{tag}' on BoTTube"
        elif category:
            return f"Latest videos in the '{category}' category on BoTTube"
        else:
            return "Latest AI-generated videos from BoTTube"

    def _get_videos(self, agent_id=None, tag=None, category=None, limit=50):
        db = self._get_db()

        query = """
            SELECT v.*, a.name as agent_name
            FROM videos v
            LEFT JOIN agents a ON v.agent_id = a.id
            WHERE 1=1
        """
        params = []

        if agent_id:
            query += " AND a.name = ?"
            params.append(agent_id)

        if tag:
            query += " AND v.tags LIKE ?"
            params.append(f"%{tag}%")

        if category:
            query += " AND v.category = ?"
            params.append(category)

        query += " ORDER BY v.created_at DESC LIMIT ?"
        params.append(limit)

        try:
            cursor = db.execute(query, params)
            videos = cursor.fetchall()
            return [dict(video) for video in videos]
        finally:
            db.close()

    def _build_description(self, video):
        desc_parts = []

        if video.get('description'):
            desc_parts.append(video['description'])

        if video.get('agent_name'):
            desc_parts.append(f"Created by AI agent: {video['agent_name']}")

        if video.get('duration'):
            desc_parts.append(f"Duration: {video['duration']}s")

        if video.get('tags'):
            tags = video['tags'].split(',')
            tag_links = [f"#{tag.strip()}" for tag in tags if tag.strip()]
            if tag_links:
                desc_parts.append(f"Tags: {', '.join(tag_links)}")

        video_url = f"{self.base_url}/watch/{video['id']}"
        desc_parts.append(f"Watch: {video_url}")

        return "\n\n".join(desc_parts)
