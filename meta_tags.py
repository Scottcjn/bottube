from urllib.parse import quote
import os

def generate_video_meta_tags(video_data, base_url):
    """Generate OpenGraph and Twitter Card meta tags for video pages"""
    video_id = video_data.get('id', '')
    title = video_data.get('title', 'BoTTube Video')
    description = video_data.get('description', '')[:200] + '...' if video_data.get('description', '') else 'Watch this video on BoTTube'
    duration = video_data.get('duration', 0)
    thumbnail_url = video_data.get('thumbnail_url', f'{base_url}/static/default-thumbnail.jpg')
    video_url = f'{base_url}/watch/{video_id}'

    # Clean title for meta tags
    clean_title = title.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
    clean_description = description.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')

    meta_tags = []

    # OpenGraph meta tags
    meta_tags.extend([
        f'<meta property="og:type" content="video.other">',
        f'<meta property="og:site_name" content="BoTTube">',
        f'<meta property="og:title" content="{clean_title}">',
        f'<meta property="og:description" content="{clean_description}">',
        f'<meta property="og:url" content="{video_url}">',
        f'<meta property="og:image" content="{thumbnail_url}">',
        f'<meta property="og:image:type" content="image/jpeg">',
        f'<meta property="og:image:width" content="1280">',
        f'<meta property="og:image:height" content="720">',
    ])

    # Video-specific OpenGraph tags
    if video_data.get('video_file'):
        video_file_url = f"{base_url}/video/{video_id}"
        meta_tags.extend([
            f'<meta property="og:video" content="{video_file_url}">',
            f'<meta property="og:video:secure_url" content="{video_file_url}">',
            f'<meta property="og:video:type" content="video/mp4">',
            f'<meta property="og:video:width" content="1280">',
            f'<meta property="og:video:height" content="720">',
        ])

    if duration:
        meta_tags.append(f'<meta property="og:video:duration" content="{duration}">')

    # Twitter Card meta tags
    meta_tags.extend([
        f'<meta name="twitter:card" content="player">',
        f'<meta name="twitter:site" content="@bottube">',
        f'<meta name="twitter:title" content="{clean_title}">',
        f'<meta name="twitter:description" content="{clean_description}">',
        f'<meta name="twitter:image" content="{thumbnail_url}">',
        f'<meta name="twitter:player" content="{base_url}/embed/{video_id}">',
        f'<meta name="twitter:player:width" content="1280">',
        f'<meta name="twitter:player:height" content="720">',
        f'<meta name="twitter:player:stream" content="{base_url}/video/{video_id}">',
        f'<meta name="twitter:player:stream:content_type" content="video/mp4">',
    ])

    return '\n    '.join(meta_tags)

def generate_channel_meta_tags(channel_data, base_url):
    """Generate OpenGraph meta tags for channel pages"""
    channel_id = channel_data.get('id', '')
    name = channel_data.get('name', 'BoTTube Channel')
    description = channel_data.get('description', '')[:200] + '...' if channel_data.get('description', '') else 'Check out this channel on BoTTube'
    avatar_url = channel_data.get('avatar_url', f'{base_url}/static/default-avatar.jpg')
    channel_url = f'{base_url}/channel/{channel_id}'

    clean_name = name.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
    clean_description = description.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')

    meta_tags = [
        f'<meta property="og:type" content="profile">',
        f'<meta property="og:site_name" content="BoTTube">',
        f'<meta property="og:title" content="{clean_name}">',
        f'<meta property="og:description" content="{clean_description}">',
        f'<meta property="og:url" content="{channel_url}">',
        f'<meta property="og:image" content="{avatar_url}">',
        f'<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:site" content="@bottube">',
        f'<meta name="twitter:title" content="{clean_name}">',
        f'<meta name="twitter:description" content="{clean_description}">',
        f'<meta name="twitter:image" content="{avatar_url}">',
    ]

    return '\n    '.join(meta_tags)

def generate_default_meta_tags(base_url, page_title='BoTTube', page_description='Decentralized video platform powered by AI'):
    """Generate default OpenGraph meta tags for homepage and other pages"""
    clean_title = page_title.replace('"', '&quot;')
    clean_description = page_description.replace('"', '&quot;')

    meta_tags = [
        f'<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="BoTTube">',
        f'<meta property="og:title" content="{clean_title}">',
        f'<meta property="og:description" content="{clean_description}">',
        f'<meta property="og:url" content="{base_url}">',
        f'<meta property="og:image" content="{base_url}/static/bottube-logo.png">',
        f'<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:site" content="@bottube">',
        f'<meta name="twitter:title" content="{clean_title}">',
        f'<meta name="twitter:description" content="{clean_description}">',
        f'<meta name="twitter:image" content="{base_url}/static/bottube-logo.png">',
    ]

    return '\n    '.join(meta_tags)

def get_base_url():
    """Get base URL from environment or default"""
    return os.environ.get('BOTTUBE_BASE_URL', 'https://bottube.ai')
