from flask import Blueprint, request, jsonify, g
import re
from bottube_server import get_db

oembed_bp = Blueprint('oembed', __name__)

@oembed_bp.route('/oembed')
def oembed():
    url = request.args.get('url')
    format_type = request.args.get('format', 'json')

    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    if format_type != 'json':
        return jsonify({'error': 'Only JSON format is supported'}), 501

    # Extract video ID from URL
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid BoTTube URL'}), 400

    # Get video metadata from database
    db = get_db()
    video = db.execute(
        'SELECT v.*, u.username FROM videos v '
        'LEFT JOIN users u ON v.user_id = u.id '
        'WHERE v.id = ?',
        (video_id,)
    ).fetchone()

    if not video:
        return jsonify({'error': 'Video not found'}), 404

    # Build OEmbed response
    thumbnail_url = f"https://bottube.ai/thumbnail/{video_id}"
    embed_html = f'''<iframe width="560" height="315" src="https://bottube.ai/embed/{video_id}" frameborder="0" allowfullscreen></iframe>'''

    oembed_data = {
        'version': '1.0',
        'type': 'video',
        'provider_name': 'BoTTube',
        'provider_url': 'https://bottube.ai',
        'title': video['title'],
        'author_name': video['username'] or 'Unknown',
        'author_url': f"https://bottube.ai/user/{video['username']}" if video['username'] else None,
        'width': 560,
        'height': 315,
        'thumbnail_url': thumbnail_url,
        'thumbnail_width': 480,
        'thumbnail_height': 360,
        'html': embed_html
    }

    # Remove None values
    oembed_data = {k: v for k, v in oembed_data.items() if v is not None}

    return jsonify(oembed_data)

def extract_video_id(url):
    """Extract video ID from BoTTube URL"""
    patterns = [
        r'https?://(?:www\.)?bottube\.ai/watch/([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?bottube\.ai/video/([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?bottube\.ai/v/([a-zA-Z0-9_-]+)'
    ]

    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            return match.group(1)

    return None
