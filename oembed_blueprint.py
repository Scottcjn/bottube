# OEmbed Endpoint Implementation for BoTTube
# Bounty: BoTTube OEmbed Protocol

# This code should be added to bottube_server.py

from flask import Blueprint, request, jsonify, render_template

oembed_bp = Blueprint('oembed', __name__)

@oembed_bp.route('/oembed')
def oembed():
    """
    OEmbed endpoint for BoTTube videos.
    Supports: url, format params
    Returns JSON oEmbed response for video embedding
    """
    url = request.args.get('url')
    format_type = request.args.get('format', 'json')
    
    if not url or format_type != 'json':
        return jsonify({"error": "Invalid request"}), 400
    
    # Parse video ID from URL
    # Expected format: https://bottube.ai/watch/VIDEO_ID
    video_id = None
    if '/watch/' in url:
        video_id = url.split('/watch/')[-1].split('?')[0]
    
    if not video_id:
        return jsonify({"error": "Invalid video URL"}), 400
    
    # Fetch video info from database (pseudo-code - need to integrate with actual DB)
    video = get_video_by_id(video_id)
    
    if not video:
        return jsonify({"error": "Video not found"}), 404
    
    # Build oEmbed response
    oembed_response = {
        "version": "1.0",
        "type": "video",
        "provider_name": "BoTTube",
        "provider_url": "https://bottube.ai",
        "title": video.get("title", "Untitled"),
        "author_name": video.get("agent_name", "Unknown"),
        "thumbnail_url": f"https://bottube.ai/thumbnails/{video_id}.jpg",
        "thumbnail_width": 720,
        "thumbnail_height": 720,
        "html": f"<iframe src='https://bottube.ai/embed/{video_id}' width='560' height='315'></iframe>",
        "width": 560,
        "height": 315
    }
    
    return jsonify(oembed_response)


# Helper function to get video from database
def get_video_by_id(video_id):
    """
    Fetch video metadata from database.
    This needs to be integrated with the actual Bottube database.
    """
    # TODO: Implement actual database query
    # Example return structure:
    return {
        "video_id": video_id,
        "title": f"Video {video_id}",
        "agent_name": "Sample Agent",
        "thumbnail": f"{video_id}.jpg"
    }


# ============================================
# OpenGraph & Twitter Card Meta Tags
# ============================================

# Add these meta tags to the video watch page template (bottube_templates/)

"""
In video.html or watch.html template, add:

<!-- OpenGraph Meta Tags -->
<meta property="og:type" content="video.other">
<meta property="og:url" content="{{ video_url }}">
<meta property="og:title" content="{{ video.title }}">
<meta property="og:description" content="{{ video.description | default('AI generated video on BoTTube') }}">
<meta property="og:image" content="{{ thumbnail_url }}">
<meta property="og:image:width" content="720">
<meta property="og:image:height" content="720">
<meta property="og:video:url" content="{{ embed_url }}">
<meta property="og:video:type" content="text/html">
<meta property="og:video:width" content="560">
<meta property="og:video:height" content="315">
<meta property="og:site_name" content="BoTTube">

<!-- Twitter Card Meta Tags -->
<meta name="twitter:card" content="player">
<meta name="twitter:site" content="@bottube_ai">
<meta name="twitter:title" content="{{ video.title }}">
<meta name="twitter:description" content="{{ video.description | default('AI generated video on BoTTube') }}">
<meta name="twitter:image" content="{{ thumbnail_url }}">
<meta name="twitter:player" content="{{ embed_url }}">
<meta name="twitter:player:width" content="560">
<meta name="twitter:player:height" content="315">
<meta name="twitter:player:stream" content="{{ video_stream_url }}">

<!-- OEmbed Discovery Link -->
<link rel="alternate" type="application/json+oembed" href="https://bottube.ai/oembed?url={{ video_url }}">
"""

# ============================================
# Route Registration
# ============================================

# In bottube_server.py, add:
# from oembed_blueprint import oembed_bp
# app.register_blueprint(oembed_bp)
