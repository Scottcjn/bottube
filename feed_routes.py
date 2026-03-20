from flask import Blueprint, Response, request, g
from feedgen.feed import FeedGenerator
from feedgen.entry import FeedEntry
import datetime
from database import get_db
import logging

feed_bp = Blueprint('feed', __name__, url_prefix='/feed')

logger = logging.getLogger(__name__)

def create_feed_generator(title_suffix=""):
    """Create base FeedGenerator with common settings"""
    fg = FeedGenerator()
    fg.id('https://bottube.com/')
    fg.title(f'BoTTube{title_suffix}')
    fg.link(href='https://bottube.com/', rel='alternate')
    fg.description('AI-generated video content from virtual agents')
    fg.language('en')
    fg.generator('BoTTube Feed Generator')
    return fg

def add_video_to_feed(fg, video):
    """Add a video entry to the feed"""
    fe = fg.add_entry()
    fe.id(f'https://bottube.com/watch/{video["id"]}')
    fe.title(video['title'] or 'Untitled Video')
    fe.link(href=f'https://bottube.com/watch/{video["id"]}')
    fe.description(video.get('description', '') or f'Video by {video.get("agent_name", "Unknown Agent")}')
    fe.author({'name': video.get('agent_name', 'BoTTube Agent')})

    if video.get('created_at'):
        try:
            created_date = datetime.datetime.fromisoformat(video['created_at'].replace('Z', '+00:00'))
            fe.published(created_date)
            fe.updated(created_date)
        except ValueError:
            fe.published(datetime.datetime.utcnow())
            fe.updated(datetime.datetime.utcnow())

@feed_bp.route('/rss')
def global_rss_feed():
    """Global RSS feed with latest 50 videos"""
    try:
        db = get_db()

        tag_filter = request.args.get('tag')
        category_filter = request.args.get('category')

        query = """
            SELECT v.id, v.title, v.description, v.created_at, a.name as agent_name
            FROM videos v
            LEFT JOIN agents a ON v.agent_id = a.id
            WHERE v.status = 'completed'
        """
        params = []

        if tag_filter:
            query += " AND (v.tags LIKE ? OR v.tags LIKE ? OR v.tags LIKE ? OR v.tags = ?)"
            params.extend([f'%,{tag_filter},%', f'{tag_filter},%', f'%,{tag_filter}', tag_filter])

        if category_filter:
            query += " AND v.category = ?"
            params.append(category_filter)

        query += " ORDER BY v.created_at DESC LIMIT 50"

        videos = db.execute(query, params).fetchall()

        title_suffix = ""
        if tag_filter:
            title_suffix = f" - {tag_filter}"
        elif category_filter:
            title_suffix = f" - {category_filter}"

        fg = create_feed_generator(title_suffix)

        for video in videos:
            add_video_to_feed(fg, dict(video))

        response = Response(fg.rss_str(pretty=True), mimetype='application/rss+xml')
        response.headers['Content-Type'] = 'application/rss+xml; charset=utf-8'
        return response

    except Exception as e:
        logger.error(f"Error generating RSS feed: {e}")
        return Response("Error generating feed", status=500)

@feed_bp.route('/atom')
def global_atom_feed():
    """Global Atom feed with latest 50 videos"""
    try:
        db = get_db()

        tag_filter = request.args.get('tag')
        category_filter = request.args.get('category')

        query = """
            SELECT v.id, v.title, v.description, v.created_at, a.name as agent_name
            FROM videos v
            LEFT JOIN agents a ON v.agent_id = a.id
            WHERE v.status = 'completed'
        """
        params = []

        if tag_filter:
            query += " AND (v.tags LIKE ? OR v.tags LIKE ? OR v.tags LIKE ? OR v.tags = ?)"
            params.extend([f'%,{tag_filter},%', f'{tag_filter},%', f'%,{tag_filter}', tag_filter])

        if category_filter:
            query += " AND v.category = ?"
            params.append(category_filter)

        query += " ORDER BY v.created_at DESC LIMIT 50"

        videos = db.execute(query, params).fetchall()

        title_suffix = ""
        if tag_filter:
            title_suffix = f" - {tag_filter}"
        elif category_filter:
            title_suffix = f" - {category_filter}"

        fg = create_feed_generator(title_suffix)

        for video in videos:
            add_video_to_feed(fg, dict(video))

        response = Response(fg.atom_str(pretty=True), mimetype='application/atom+xml')
        response.headers['Content-Type'] = 'application/atom+xml; charset=utf-8'
        return response

    except Exception as e:
        logger.error(f"Error generating Atom feed: {e}")
        return Response("Error generating feed", status=500)

@feed_bp.route('/rss/<agent_slug>')
def agent_rss_feed(agent_slug):
    """Per-agent RSS feed"""
    try:
        db = get_db()

        agent = db.execute('SELECT * FROM agents WHERE slug = ?', (agent_slug,)).fetchone()
        if not agent:
            return Response("Agent not found", status=404)

        videos = db.execute("""
            SELECT v.id, v.title, v.description, v.created_at, a.name as agent_name
            FROM videos v
            LEFT JOIN agents a ON v.agent_id = a.id
            WHERE v.agent_id = ? AND v.status = 'completed'
            ORDER BY v.created_at DESC LIMIT 50
        """, (agent['id'],)).fetchall()

        fg = create_feed_generator(f" - {agent['name']}")

        for video in videos:
            add_video_to_feed(fg, dict(video))

        response = Response(fg.rss_str(pretty=True), mimetype='application/rss+xml')
        response.headers['Content-Type'] = 'application/rss+xml; charset=utf-8'
        return response

    except Exception as e:
        logger.error(f"Error generating agent RSS feed: {e}")
        return Response("Error generating feed", status=500)

@feed_bp.route('/atom/<agent_slug>')
def agent_atom_feed(agent_slug):
    """Per-agent Atom feed"""
    try:
        db = get_db()

        agent = db.execute('SELECT * FROM agents WHERE slug = ?', (agent_slug,)).fetchone()
        if not agent:
            return Response("Agent not found", status=404)

        videos = db.execute("""
            SELECT v.id, v.title, v.description, v.created_at, a.name as agent_name
            FROM videos v
            LEFT JOIN agents a ON v.agent_id = a.id
            WHERE v.agent_id = ? AND v.status = 'completed'
            ORDER BY v.created_at DESC LIMIT 50
        """, (agent['id'],)).fetchall()

        fg = create_feed_generator(f" - {agent['name']}")

        for video in videos:
            add_video_to_feed(fg, dict(video))

        response = Response(fg.atom_str(pretty=True), mimetype='application/atom+xml')
        response.headers['Content-Type'] = 'application/atom+xml; charset=utf-8'
        return response

    except Exception as e:
        logger.error(f"Error generating agent Atom feed: {e}")
        return Response("Error generating feed", status=500)
