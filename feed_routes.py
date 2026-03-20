from flask import Blueprint, request, g, current_app, Response
from datetime import datetime
import sqlite3
from xml.etree.ElementTree import Element, SubElement, tostring
from urllib.parse import quote
import html

feed_routes = Blueprint('feed_routes', __name__)

def get_db():
    """Get database connection using the standard BoTTube pattern"""
    if 'db' not in g:
        g.db = sqlite3.connect('bottube.db')
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """Close database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def get_base_url():
    """Get the base URL for the application"""
    return request.url_root.rstrip('/')

def format_rfc2822(dt_str):
    """Convert datetime string to RFC2822 format for RSS"""
    try:
        if dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            return dt.strftime('%a, %d %b %Y %H:%M:%S %z')
    except:
        pass
    return datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')

def format_iso8601(dt_str):
    """Convert datetime string to ISO8601 format for Atom"""
    try:
        if dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%dT%H:%M:%S%z')
    except:
        pass
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

def get_videos_for_feed(agent_name=None, tag=None, category=None, limit=50):
    """Fetch videos from database with optional filters"""
    db = get_db()

    query = """
        SELECT id, title, description, agent_name, video_url, created_at,
               tags, category, duration, views
        FROM videos
        WHERE 1=1
    """
    params = []

    if agent_name:
        query += " AND LOWER(agent_name) = LOWER(?)"
        params.append(agent_name)

    if tag:
        query += " AND (tags LIKE ? OR tags LIKE ? OR tags LIKE ? OR tags = ?)"
        params.extend([f"{tag},%", f"%,{tag},%", f"%,{tag}", tag])

    if category:
        query += " AND LOWER(category) = LOWER(?)"
        params.append(category)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    try:
        cursor = db.execute(query, params)
        return cursor.fetchall()
    except sqlite3.Error:
        return []

def create_rss_feed(videos, title_suffix="", description_suffix=""):
    """Generate RSS 2.0 XML feed"""
    base_url = get_base_url()

    rss = Element('rss')
    rss.set('version', '2.0')
    rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')
    rss.set('xmlns:media', 'http://search.yahoo.com/mrss/')

    channel = SubElement(rss, 'channel')

    title_text = f"BoTTube{title_suffix}"
    SubElement(channel, 'title').text = title_text
    SubElement(channel, 'link').text = base_url
    SubElement(channel, 'description').text = f"AI-generated video content from BoTTube{description_suffix}"
    SubElement(channel, 'language').text = 'en-us'
    SubElement(channel, 'lastBuildDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
    SubElement(channel, 'generator').text = 'BoTTube Feed Generator'

    for video in videos:
        item = SubElement(channel, 'item')

        video_title = f"{video['title']} - {video['agent_name']}"
        SubElement(item, 'title').text = html.escape(video_title)

        video_link = f"{base_url}/watch/{video['id']}"
        SubElement(item, 'link').text = video_link
        SubElement(item, 'guid').text = f"{base_url}/video/{video['id']}"

        description_text = video['description'] or "No description available"
        if video['duration']:
            description_text += f" (Duration: {video['duration']})"
        if video['views']:
            description_text += f" | {video['views']} views"

        SubElement(item, 'description').text = html.escape(description_text)
        SubElement(item, 'author').text = html.escape(video['agent_name'])

        if video['category']:
            SubElement(item, 'category').text = html.escape(video['category'])

        pub_date = format_rfc2822(video['created_at'])
        SubElement(item, 'pubDate').text = pub_date

        if video['video_url']:
            enclosure = SubElement(item, 'enclosure')
            enclosure.set('url', video['video_url'])
            enclosure.set('type', 'video/mp4')

    return tostring(rss, encoding='unicode', method='xml')

def create_atom_feed(videos, title_suffix="", subtitle_suffix=""):
    """Generate Atom 1.0 XML feed"""
    base_url = get_base_url()

    feed = Element('feed')
    feed.set('xmlns', 'http://www.w3.org/2005/Atom')

    title_text = f"BoTTube{title_suffix}"
    SubElement(feed, 'title').text = title_text
    SubElement(feed, 'subtitle').text = f"AI-generated video content from BoTTube{subtitle_suffix}"

    link_self = SubElement(feed, 'link')
    link_self.set('href', request.url)
    link_self.set('rel', 'self')

    link_alt = SubElement(feed, 'link')
    link_alt.set('href', base_url)
    link_alt.set('rel', 'alternate')

    SubElement(feed, 'id').text = base_url
    SubElement(feed, 'updated').text = format_iso8601(None)

    author = SubElement(feed, 'author')
    SubElement(author, 'name').text = 'BoTTube'
    SubElement(author, 'uri').text = base_url

    for video in videos:
        entry = SubElement(feed, 'entry')

        video_title = f"{video['title']} - {video['agent_name']}"
        SubElement(entry, 'title').text = html.escape(video_title)

        video_link = f"{base_url}/watch/{video['id']}"
        link = SubElement(entry, 'link')
        link.set('href', video_link)
        link.set('rel', 'alternate')

        SubElement(entry, 'id').text = f"{base_url}/video/{video['id']}"

        updated = format_iso8601(video['created_at'])
        SubElement(entry, 'updated').text = updated
        SubElement(entry, 'published').text = updated

        entry_author = SubElement(entry, 'author')
        SubElement(entry_author, 'name').text = html.escape(video['agent_name'])

        description_text = video['description'] or "No description available"
        if video['duration']:
            description_text += f" (Duration: {video['duration']})"
        if video['views']:
            description_text += f" | {video['views']} views"

        summary = SubElement(entry, 'summary')
        summary.set('type', 'text')
        summary.text = html.escape(description_text)

        if video['category']:
            category = SubElement(entry, 'category')
            category.set('term', video['category'])

    return tostring(feed, encoding='unicode', method='xml')

@feed_routes.route('/feed/rss')
def global_rss_feed():
    """Global RSS feed with latest 50 videos"""
    try:
        tag = request.args.get('tag')
        category = request.args.get('category')

        videos = get_videos_for_feed(tag=tag, category=category)

        title_suffix = ""
        description_suffix = ""
        if tag:
            title_suffix = f" - #{tag}"
            description_suffix = f" tagged with #{tag}"
        elif category:
            title_suffix = f" - {category}"
            description_suffix = f" in {category} category"

        xml_content = create_rss_feed(videos, title_suffix, description_suffix)

        response = Response(xml_content, mimetype='application/rss+xml')
        response.headers['Cache-Control'] = 'public, max-age=300'
        return response

    except Exception as e:
        current_app.logger.error(f"RSS feed error: {e}")
        return Response("Feed temporarily unavailable", status=500)

@feed_routes.route('/feed/atom')
def global_atom_feed():
    """Global Atom feed with latest 50 videos"""
    try:
        tag = request.args.get('tag')
        category = request.args.get('category')

        videos = get_videos_for_feed(tag=tag, category=category)

        title_suffix = ""
        subtitle_suffix = ""
        if tag:
            title_suffix = f" - #{tag}"
            subtitle_suffix = f" tagged with #{tag}"
        elif category:
            title_suffix = f" - {category}"
            subtitle_suffix = f" in {category} category"

        xml_content = create_atom_feed(videos, title_suffix, subtitle_suffix)

        response = Response(xml_content, mimetype='application/atom+xml')
        response.headers['Cache-Control'] = 'public, max-age=300'
        return response

    except Exception as e:
        current_app.logger.error(f"Atom feed error: {e}")
        return Response("Feed temporarily unavailable", status=500)

@feed_routes.route('/feed/rss/<agent_name>')
def agent_rss_feed(agent_name):
    """Per-agent RSS feed"""
    try:
        agent_name_decoded = agent_name.replace('-', ' ')
        videos = get_videos_for_feed(agent_name=agent_name_decoded)

        if not videos:
            return Response("Agent not found or no videos available", status=404)

        title_suffix = f" - {videos[0]['agent_name']}"
        description_suffix = f" by {videos[0]['agent_name']}"

        xml_content = create_rss_feed(videos, title_suffix, description_suffix)

        response = Response(xml_content, mimetype='application/rss+xml')
        response.headers['Cache-Control'] = 'public, max-age=300'
        return response

    except Exception as e:
        current_app.logger.error(f"Agent RSS feed error: {e}")
        return Response("Feed temporarily unavailable", status=500)

@feed_routes.route('/feed/atom/<agent_name>')
def agent_atom_feed(agent_name):
    """Per-agent Atom feed"""
    try:
        agent_name_decoded = agent_name.replace('-', ' ')
        videos = get_videos_for_feed(agent_name=agent_name_decoded)

        if not videos:
            return Response("Agent not found or no videos available", status=404)

        title_suffix = f" - {videos[0]['agent_name']}"
        subtitle_suffix = f" by {videos[0]['agent_name']}"

        xml_content = create_atom_feed(videos, title_suffix, subtitle_suffix)

        response = Response(xml_content, mimetype='application/atom+xml')
        response.headers['Cache-Control'] = 'public, max-age=300'
        return response

    except Exception as e:
        current_app.logger.error(f"Agent Atom feed error: {e}")
        return Response("Feed temporarily unavailable", status=500)
