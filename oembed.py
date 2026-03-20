import re
from urllib.parse import urlparse, parse_qs
from flask import Blueprint, request, jsonify, g
from database import get_db

oembed_bp = Blueprint('oembed', __name__)

def extract_video_id(url):
    """Extract video ID from various BoTTube URL formats"""
    parsed = urlparse(url)

    # Handle /watch/VIDEO_ID format
    if parsed.path.startswith('/watch/'):
        return parsed.path.split('/watch/')[-1]

    # Handle /watch?v=VIDEO_ID format
    if parsed.path == '/watch':
        query_params = parse_qs(parsed.query)
        if 'v' in query_params:
            return query_params['v'][0]

    return None

def get_video_metadata(video_id):
    """Get video metadata from database"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT title, description, thumbnail_url, duration, view_count,
               upload_date, channel_name
        FROM videos
        WHERE video_id = ?
    """, (video_id,))

    return cursor.fetchone()

@oembed_bp.route('/oembed')
def oembed_endpoint():
    url = request.args.get('url')
    format_type = request.args.get('format', 'json')

    if not url:
        return jsonify({'error': 'url parameter is required'}), 400

    if format_type != 'json':
        return jsonify({'error': 'Only JSON format is supported'}), 501

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid BoTTube URL'}), 400

    video_data = get_video_metadata(video_id)
    if not video_data:
        return jsonify({'error': 'Video not found'}), 404

    title, description, thumbnail_url, duration, view_count, upload_date, channel_name = video_data

    # Build embed HTML
    embed_html = f'''
    <iframe width="560" height="315"
            src="https://bottube.ai/embed/{video_id}"
            frameborder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowfullscreen>
    </iframe>
    '''

    response_data = {
        "version": "1.0",
        "type": "video",
        "provider_name": "BoTTube",
        "provider_url": "https://bottube.ai",
        "title": title,
        "author_name": channel_name,
        "width": 560,
        "height": 315,
        "html": embed_html.strip()
    }

    # Add optional fields if available
    if thumbnail_url:
        response_data["thumbnail_url"] = thumbnail_url
        response_data["thumbnail_width"] = 480
        response_data["thumbnail_height"] = 360

    if description:
        # Truncate description for preview
        desc = description[:200] + "..." if len(description) > 200 else description
        response_data["description"] = desc

    if duration:
        response_data["duration"] = duration

    return jsonify(response_data)
