# SPDX-License-Identifier: MIT
# OEmbed Protocol Support for BoTTube
# Bounty: 5-10 RTC

import re
import requests
from flask import Blueprint, request, jsonify

oembed_bp = Blueprint("oembed", __name__)

BOTTUBE_URL = "https://bottube.ai"


def _extract_video_id(url: str) -> str | None:
    """Extract video ID from various BoTTube URL formats."""
    patterns = [
        r"bottube\.ai/watch/([a-zA-Z0-9_-]+)",
        r"bottube\.ai/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _fetch_video_info(video_id: str) -> dict | None:
    """Fetch video metadata from BoTTube API."""
    try:
        api_url = f"{BOTTUBE_URL}/api/videos/{video_id}"
        resp = requests.get(api_url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


@oembed_bp.route("/oembed")
def oembed_endpoint():
    """
    OEmbed endpoint for BoTTube video embeds.
    
    Usage:
    GET https://bottube.ai/oembed?url=https://bottube.ai/watch/VIDEO_ID&format=json
    """
    url = request.args.get("url")
    format_type = request.args.get("format", "json")
    
    if not url:
        return jsonify({"error": "url parameter required"}), 400
    
    video_id = _extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid BoTTube URL"}), 400
    
    video = _fetch_video_info(video_id)
    if not video:
        return jsonify({"error": "Video not found"}), 404
    
    # Build OEmbed response
    response = {
        "version": "1.0",
        "type": "video",
        "provider_name": "BoTTube",
        "provider_url": BOTTUBE_URL,
        "title": video.get("title", "Untitled"),
        "author_name": video.get("agent_name", "AI Agent"),
        "author_url": f"{BOTTUBE_URL}/agent/{video.get('agent_name', '')}",
        "thumbnail_url": video.get("thumbnail_url", f"{BOTTUBE_URL}/thumbnails/{video_id}.jpg"),
        "thumbnail_width": 720,
        "thumbnail_height": 720,
        "html": f"<iframe src='{BOTTUBE_URL}/embed/{video_id}' width='560' height='315' frameborder='0' allowfullscreen></iframe>",
        "width": 560,
        "height": 315,
    }
    
    if format_type == "xml":
        # Return XML format
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<oembed>
  <version>1.0</version>
  <type>video</type>
  <provider_name>BoTTube</provider_name>
  <provider_url>{BOTTUBE_URL}</provider_url>
  <title>{response['title']}</title>
  <author_name>{response['author_name']}</author_name>
  <thumbnail_url>{response['thumbnail_url']}</thumbnail_url>
  <thumbnail_width>{response['thumbnail_width']}</thumbnail_width>
  <thumbnail_height>{response['thumbnail_height']}</thumbnail_height>
  <html><![CDATA[{response['html']}]]></html>
  <width>{response['width']}</width>
  <height>{response['height']}</height>
</oembed>"""
        return xml, 200, {"Content-Type": "application/xml"}
    
    return jsonify(response)
