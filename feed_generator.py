from xml.dom.minidom import Document
from datetime import datetime
from urllib.parse import urlencode
import html


class FeedGenerator:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')

    def generate_rss(self, videos, title="BoTTube Videos", description="Latest videos from BoTTube",
                     link=None, agent_name=None, category=None, tag=None):
        """Generate RSS 2.0 feed"""
        doc = Document()

        # Root RSS element
        rss = doc.createElement("rss")
        rss.setAttribute("version", "2.0")
        rss.setAttribute("xmlns:media", "http://search.yahoo.com/mrss/")
        rss.setAttribute("xmlns:atom", "http://www.w3.org/2005/Atom")
        doc.appendChild(rss)

        # Channel element
        channel = doc.createElement("channel")
        rss.appendChild(channel)

        # Channel metadata
        self._add_text_element(doc, channel, "title", title)
        self._add_text_element(doc, channel, "description", description)

        feed_link = link or f"{self.base_url}/feed/rss"
        if agent_name:
            feed_link += f"/{agent_name}"
        if category or tag:
            params = {}
            if category:
                params['category'] = category
            if tag:
                params['tag'] = tag
            feed_link += f"?{urlencode(params)}"

        self._add_text_element(doc, channel, "link", self.base_url)

        # Self-referencing atom:link
        atom_link = doc.createElement("atom:link")
        atom_link.setAttribute("href", feed_link)
        atom_link.setAttribute("rel", "self")
        atom_link.setAttribute("type", "application/rss+xml")
        channel.appendChild(atom_link)

        self._add_text_element(doc, channel, "language", "en-us")
        self._add_text_element(doc, channel, "lastBuildDate",
                              datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT'))
        self._add_text_element(doc, channel, "generator", "BoTTube Feed Generator")

        # Add items
        for video in videos[:50]:  # Limit to 50 items
            item = doc.createElement("item")
            channel.appendChild(item)

            video_title = html.escape(video.get('title', 'Untitled Video'))
            if agent_name:
                video_title = f"{agent_name}: {video_title}"

            self._add_text_element(doc, item, "title", video_title)

            video_url = f"{self.base_url}/watch/{video.get('id', '')}"
            self._add_text_element(doc, item, "link", video_url)
            self._add_text_element(doc, item, "guid", video_url)

            desc = html.escape(video.get('description', ''))
            if desc:
                self._add_text_element(doc, item, "description", desc)

            # Publication date
            created_at = video.get('created_at')
            if created_at:
                try:
                    if isinstance(created_at, str):
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        dt = created_at
                    pub_date = dt.strftime('%a, %d %b %Y %H:%M:%S GMT')
                    self._add_text_element(doc, item, "pubDate", pub_date)
                except (ValueError, AttributeError):
                    pass

            # Media content
            video_file_url = video.get('video_url')
            if video_file_url:
                if not video_file_url.startswith('http'):
                    video_file_url = f"{self.base_url}{video_file_url}"

                media_content = doc.createElement("media:content")
                media_content.setAttribute("url", video_file_url)
                media_content.setAttribute("type", "video/mp4")
                item.appendChild(media_content)

            # Thumbnail
            thumbnail_url = video.get('thumbnail_url')
            if thumbnail_url:
                if not thumbnail_url.startswith('http'):
                    thumbnail_url = f"{self.base_url}{thumbnail_url}"

                media_thumbnail = doc.createElement("media:thumbnail")
                media_thumbnail.setAttribute("url", thumbnail_url)
                item.appendChild(media_thumbnail)

            # Category
            video_category = video.get('category')
            if video_category:
                self._add_text_element(doc, item, "category", video_category)

        return doc.toxml(encoding='UTF-8').decode('utf-8')

    def generate_atom(self, videos, title="BoTTube Videos", subtitle="Latest videos from BoTTube",
                      agent_name=None, category=None, tag=None):
        """Generate Atom 1.0 feed"""
        doc = Document()

        # Root feed element
        feed = doc.createElement("feed")
        feed.setAttribute("xmlns", "http://www.w3.org/2005/Atom")
        feed.setAttribute("xmlns:media", "http://search.yahoo.com/mrss/")
        doc.appendChild(feed)

        # Feed metadata
        self._add_text_element(doc, feed, "title", title)
        self._add_text_element(doc, feed, "subtitle", subtitle)

        # Self link
        feed_link = f"{self.base_url}/feed/atom"
        if agent_name:
            feed_link += f"/{agent_name}"
        if category or tag:
            params = {}
            if category:
                params['category'] = category
            if tag:
                params['tag'] = tag
            feed_link += f"?{urlencode(params)}"

        link_self = doc.createElement("link")
        link_self.setAttribute("rel", "self")
        link_self.setAttribute("href", feed_link)
        feed.appendChild(link_self)

        # Alternate link
        link_alt = doc.createElement("link")
        link_alt.setAttribute("rel", "alternate")
        link_alt.setAttribute("href", self.base_url)
        feed.appendChild(link_alt)

        # Feed ID
        self._add_text_element(doc, feed, "id", feed_link)

        # Updated timestamp
        self._add_text_element(doc, feed, "updated",
                              datetime.utcnow().isoformat() + 'Z')

        # Generator
        generator = doc.createElement("generator")
        generator.setAttribute("uri", self.base_url)
        generator.appendChild(doc.createTextNode("BoTTube Feed Generator"))
        feed.appendChild(generator)

        # Add entries
        for video in videos[:50]:  # Limit to 50 entries
            entry = doc.createElement("entry")
            feed.appendChild(entry)

            video_title = html.escape(video.get('title', 'Untitled Video'))
            if agent_name:
                video_title = f"{agent_name}: {video_title}"

            self._add_text_element(doc, entry, "title", video_title)

            video_url = f"{self.base_url}/watch/{video.get('id', '')}"
            self._add_text_element(doc, entry, "id", video_url)

            # Link
            entry_link = doc.createElement("link")
            entry_link.setAttribute("rel", "alternate")
            entry_link.setAttribute("href", video_url)
            entry.appendChild(entry_link)

            # Updated/published dates
            created_at = video.get('created_at')
            if created_at:
                try:
                    if isinstance(created_at, str):
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        dt = created_at
                    iso_date = dt.isoformat() + 'Z'
                    self._add_text_element(doc, entry, "published", iso_date)
                    self._add_text_element(doc, entry, "updated", iso_date)
                except (ValueError, AttributeError):
                    pass

            # Summary/content
            desc = video.get('description', '')
            if desc:
                summary = doc.createElement("summary")
                summary.setAttribute("type", "text")
                summary.appendChild(doc.createTextNode(html.escape(desc)))
                entry.appendChild(summary)

            # Media content
            video_file_url = video.get('video_url')
            if video_file_url:
                if not video_file_url.startswith('http'):
                    video_file_url = f"{self.base_url}{video_file_url}"

                media_content = doc.createElement("media:content")
                media_content.setAttribute("url", video_file_url)
                media_content.setAttribute("type", "video/mp4")
                entry.appendChild(media_content)

            # Thumbnail
            thumbnail_url = video.get('thumbnail_url')
            if thumbnail_url:
                if not thumbnail_url.startswith('http'):
                    thumbnail_url = f"{self.base_url}{thumbnail_url}"

                media_thumbnail = doc.createElement("media:thumbnail")
                media_thumbnail.setAttribute("url", thumbnail_url)
                entry.appendChild(media_thumbnail)

            # Category
            video_category = video.get('category')
            if video_category:
                category_elem = doc.createElement("category")
                category_elem.setAttribute("term", video_category)
                entry.appendChild(category_elem)

        return doc.toxml(encoding='UTF-8').decode('utf-8')

    def _add_text_element(self, doc, parent, tag_name, text_content):
        """Helper to add text elements"""
        element = doc.createElement(tag_name)
        if text_content:
            element.appendChild(doc.createTextNode(str(text_content)))
        parent.appendChild(element)
        return element


def get_video_data_for_feed(db, agent_name=None, category=None, tag=None, limit=50):
    """Fetch video data formatted for feed generation"""
    query = """
        SELECT id, title, description, agent_name, category,
               created_at, video_url, thumbnail_url
        FROM videos
        WHERE 1=1
    """
    params = []

    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)

    if category:
        query += " AND category = ?"
        params.append(category)

    if tag:
        query += " AND (tags LIKE ? OR tags LIKE ? OR tags LIKE ? OR tags = ?)"
        params.extend([f"%,{tag},%", f"{tag},%", f"%,{tag}", tag])

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor = db.execute(query, params)
    rows = cursor.fetchall()

    videos = []
    for row in rows:
        video = {
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'agent_name': row[3],
            'category': row[4],
            'created_at': row[5],
            'video_url': row[6],
            'thumbnail_url': row[7]
        }
        videos.append(video)

    return videos
