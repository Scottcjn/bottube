"""Utility module for generating OpenGraph and Twitter Card meta tags."""

from urllib.parse import quote


def generate_video_meta_tags(video_id, title, description, thumbnail_url=None, duration=None, base_url="https://bottube.ai"):
    """Generate meta tags for a video page."""
    video_url = f"{base_url}/watch/{video_id}"
    escaped_title = quote(title) if title else "BoTTube Video"
    escaped_description = quote(description[:160] + "..." if description and len(description) > 160 else description or "")

    # Basic OpenGraph tags
    meta_tags = [
        f'<meta property="og:type" content="video.other">',
        f'<meta property="og:title" content="{escaped_title}">',
        f'<meta property="og:description" content="{escaped_description}">',
        f'<meta property="og:url" content="{video_url}">',
        f'<meta property="og:site_name" content="BoTTube">',
        f'<meta property="og:video" content="{video_url}">',
        f'<meta property="og:video:secure_url" content="{video_url}">',
        f'<meta property="og:video:type" content="text/html">',
    ]

    # Add thumbnail if available
    if thumbnail_url:
        meta_tags.extend([
            f'<meta property="og:image" content="{thumbnail_url}">',
            f'<meta property="og:image:width" content="1280">',
            f'<meta property="og:image:height" content="720">',
        ])

    # Add duration if available
    if duration:
        meta_tags.append(f'<meta property="video:duration" content="{duration}">')

    # Twitter Card tags
    meta_tags.extend([
        f'<meta name="twitter:card" content="player">',
        f'<meta name="twitter:site" content="@bottube">',
        f'<meta name="twitter:title" content="{escaped_title}">',
        f'<meta name="twitter:description" content="{escaped_description}">',
        f'<meta name="twitter:player" content="{video_url}">',
        f'<meta name="twitter:player:width" content="1280">',
        f'<meta name="twitter:player:height" content="720">',
    ])

    if thumbnail_url:
        meta_tags.append(f'<meta name="twitter:image" content="{thumbnail_url}">')

    # OEmbed discovery link
    oembed_url = f"{base_url}/oembed?url={quote(video_url)}&format=json"
    meta_tags.append(f'<link rel="alternate" type="application/json+oembed" href="{oembed_url}" title="{escaped_title}">')

    return "\n    ".join(meta_tags)


def get_video_meta_data(video_id, db_connection):
    """Fetch video metadata from database for meta tag generation."""
    cursor = db_connection.execute(
        'SELECT title, description, thumbnail_path, duration FROM videos WHERE id = ?',
        (video_id,)
    )
    video = cursor.fetchone()

    if not video:
        return None

    return {
        'title': video['title'],
        'description': video['description'],
        'thumbnail_url': f"/static/thumbnails/{video['thumbnail_path']}" if video['thumbnail_path'] else None,
        'duration': video['duration']
    }
