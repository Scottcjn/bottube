from flask import Blueprint, request, jsonify, g
from urllib.parse import urlparse, parse_qs
import re
from bottube_server import get_db

oembed_bp = Blueprint('oembed', __name__)

@oembed_bp.route('/oembed')
def oembed_endpoint():
    url = request.args.get('url')
    format_type = request.args.get('format', 'json')

    if not url:
        return jsonify({'error': 'url parameter is required'}), 400

    if format_type != 'json':
        return jsonify({'error': 'Only JSON format is supported'}), 400

    # Extract video ID from URL
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid BoTTube URL'}), 400

    # Get video data from database
    db = get_db()
    video = db.execute(
        'SELECT id, title, description, thumbnail_path, duration, created_at, user_id '
        'FROM videos WHERE id = ?',
        (video_id,)
    ).fetchone()

    if not video:
        return jsonify({'error': 'Video not found'}), 404

    # Get creator info
    creator = db.execute(
        'SELECT username FROM users WHERE id = ?',
        (video['user_id'],)
    ).fetchone()

    # Build OEmbed response
    response_data = {
        'version': '1.0',
        'type': 'video',
        'provider_name': 'BoTTube',
        'provider_url': 'https://bottube.ai',
        'title': video['title'],
        'author_name': creator['username'] if creator else 'Unknown',
        'author_url': f"https://bottube.ai/user/{creator['username']}" if creator else None,
        'width': 640,
        'height': 360,
        'html': f'<iframe src="https://bottube.ai/embed/{video_id}" width="640" height="360" frameborder="0" allowfullscreen></iframe>',
        'thumbnail_url': f"https://bottube.ai{video['thumbnail_path']}" if video['thumbnail_path'] else None,
        'thumbnail_width': 480,
        'thumbnail_height': 360
    }

    # Add optional fields if available
    if video['description']:
        response_data['description'] = video['description'][:200] + '...' if len(video['description']) > 200 else video['description']

    if video['duration']:
        response_data['duration'] = video['duration']

    return jsonify(response_data)

def extract_video_id(url):
    """Extract video ID from BoTTube URL"""
    parsed = urlparse(url)

    # Handle /watch/VIDEO_ID format
    watch_match = re.match(r'^/watch/([a-zA-Z0-9_-]+)$', parsed.path)
    if watch_match:
        return watch_match.group(1)

    # Handle /embed/VIDEO_ID format
    embed_match = re.match(r'^/embed/([a-zA-Z0-9_-]+)$', parsed.path)
    if embed_match:
        return embed_match.group(1)

    # Handle query parameter format (?v=VIDEO_ID)
    if parsed.query:
        query_params = parse_qs(parsed.query)
        if 'v' in query_params:
            return query_params['v'][0]

    return None
