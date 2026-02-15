#!/usr/bin/env python3
"""
BoTTube RSS/Atom Feed Generator
Standalone script that generates RSS feeds from BoTTube API
"""

import os
import sys
import json
import time
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from dataclasses import dataclass
from typing import List, Optional
import requests

# Configuration
BOTTUBE_API = os.environ.get('BOTTUBE_API', 'https://bottube.ai/api')
CACHE_FILE = 'bottube_feed_cache.json'
CACHE_TTL = 300  # 5 minutes


@dataclass
class Video:
    """Represents a BoTTube video"""
    id: str
    title: str
    description: str
    thumbnail: str
    video_url: str
    watch_url: str
    published_at: str
    author: str
    category: str
    duration: int = 0


def get_videos(agent: str = None, category: str = None, limit: int = 20) -> List[Video]:
    """Fetch videos from BoTTube API"""
    videos = []
    
    params = {'limit': limit}
    if agent:
        params['agent'] = agent
    if category:
        params['category'] = category
    
    try:
        resp = requests.get(f"{BOTTUBE_API}/videos", params=params, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get('videos', []):
                videos.append(Video(
                    id=item.get('id', ''),
                    title=item.get('title', 'Untitled'),
                    description=item.get('description', ''),
                    thumbnail=item.get('thumbnail', ''),
                    video_url=f"https://bottube.ai/api/videos/{item.get('id', '')}/stream",
                    watch_url=f"https://bottube.ai/watch/{item.get('id', '')}",
                    published_at=item.get('published_at', datetime.now().isoformat()),
                    author=item.get('agent', {}).get('name', 'Unknown') if isinstance(item.get('agent'), dict) else str(item.get('agent', 'Unknown')),
                    category=item.get('category', 'uncategorized'),
                    duration=item.get('duration', 0)
                ))
    except Exception as e:
        print(f"Error fetching videos: {e}", file=sys.stderr)
    
    # Return demo data if no videos found
    if not videos:
        videos = get_demo_videos()
    
    return videos


def get_demo_videos() -> List[Video]:
    """Return demo videos for testing"""
    return [
        Video(
            id='demo001',
            title='AI Agent Demo Video 1',
            description='First demo video for testing RSS feed',
            thumbnail='https://bottube.ai/thumbnails/demo001.jpg',
            video_url='https://bottube.ai/api/videos/demo001/stream',
            watch_url='https://bottube.ai/watch/demo001',
            published_at=datetime.now().isoformat(),
            author='TestAgent',
            category='technology',
            duration=300
        ),
        Video(
            id='demo002',
            title='Bot Trading Results',
            description='Daily trading results from AI agent',
            thumbnail='https://bottube.ai/thumbnails/demo002.jpg',
            video_url='https://bottube.ai/api/videos/demo002/stream',
            watch_url='https://bottube.ai/watch/demo002',
            published_at=datetime.now().isoformat(),
            author='TraderBot',
            category='finance',
            duration=180
        ),
    ]


def generate_rss_feed(videos: List[Video], title: str, description: str, 
                      feed_url: str, site_url: str = 'https://bottube.ai') -> str:
    """Generate RSS 2.0 feed"""
    
    # RSS root element
    rss = Element('rss', {
        'version': '2.0',
        'xmlns:atom': 'http://www.w3.org/2005/Atom',
        'xmlns:media': 'http://search.yahoo.com/mrss/',
    })
    
    # Channel
    channel = SubElement(rss, 'channel')
    
    # Channel metadata
    title_elem = SubElement(channel, 'title')
    title_elem.text = title
    
    desc_elem = SubElement(channel, 'description')
    desc_elem.text = description
    
    link_elem = SubElement(channel, 'link')
    link_elem.text = site_url
    
    # Atom self-link
    atom_link = SubElement(channel, 'atom:link', {
        'href': feed_url,
        'rel': 'self',
        'type': 'application/rss+xml'
    })
    
    # Language and dates
    lang_elem = SubElement(channel, 'language')
    lang_elem.text = 'en-us'
    
    update_elem = SubElement(channel, 'lastBuildDate')
    update_elem.text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
    
    generator_elem = SubElement(channel, 'generator')
    generator_elem.text = 'BoTTube RSS Generator'
    
    # Videos
    for video in videos[:20]:  # Limit to 20 items
        item = SubElement(channel, 'item')
        
        # Title
        item_title = SubElement(item, 'title')
        item_title.text = video.title
        
        # Description
        item_desc = SubElement(item, 'description')
        item_desc.text = f"<p>{video.description}</p>"
        
        # Link
        item_link = SubElement(item, 'link')
        item_link.text = video.watch_url
        
        # GUID
        guid = SubElement(item, 'guid', {'isPermaLink': 'false'})
        guid.text = video.id
        
        # Publication date
        pub_date = SubElement(item, 'pubDate')
        try:
            dt = datetime.fromisoformat(video.published_at.replace('Z', '+00:00'))
            pub_date.text = dt.strftime('%a, %d %b %Y %H:%M:%S GMT')
        except:
            pub_date.text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        # Author
        author = SubElement(item, 'author')
        author.text = video.author
        
        # Category
        category = SubElement(item, 'category')
        category.text = video.category
        
        # Thumbnail via media:thumbnail
        if video.thumbnail:
            media_thumb = SubElement(item, '{http://search.yahoo.com/mrss/}thumbnail', {
                'url': video.thumbnail
            })
        
        # Video enclosure
        if video.video_url:
            enclosure = SubElement(item, 'enclosure', {
                'url': video.video_url,
                'type': 'video/mp4',
                'length': str(video.duration * 1000)  # ms
            })
        
        # Media content
        if video.thumbnail:
            media_content = SubElement(item, '{http://search.yahoo.com/mrss/}content', {
                'url': video.video_url,
                'type': 'video/mp4',
                'medium': 'video',
                'duration': str(video.duration)
            })
    
    # Pretty print
    rough = tostring(rss, encoding='unicode')
    reparsed = minidom.parseString(rough)
    return reparsed.toprettyxml(indent='  ')


def generate_atom_feed(videos: List[Video], title: str, description: str,
                       feed_url: str, site_url: str = 'https://bottube.ai') -> str:
    """Generate Atom 1.0 feed"""
    
    # Feed root
    feed = Element('{http://www.w3.org/2005/Atom}feed', {
        'xmlns': 'http://www.w3.org/2005/Atom',
    })
    
    # Metadata
    feed_title = SubElement(feed, 'title')
    feed_title.text = title
    
    subtitle = SubElement(feed, 'subtitle')
    subtitle.text = description
    
    link = SubElement(feed, 'link', {
        'href': site_url,
        'rel': 'alternate'
    })
)
    
    self_link = SubElement(feed, 'link', {
        'href': feed_url,
        'rel': 'self',
        'type': 'application/atom+xml'
    })
    
    id_elem = SubElement(feed, 'id')
    id_elem.text = feed_url
    
    updated = SubElement(feed, 'updated')
    updated.text = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    generator = SubElement(feed, 'generator')
    generator.text = 'BoTTube Atom Generator'
    
    # Entries
    for video in videos[:20]:
        entry = SubElement(feed, 'entry')
        
        entry_title = SubElement(entry, 'title')
        entry_title.text = video.title
        
        link_elem = SubElement(entry, 'link', {
            'href': video.watch_url,
            'rel': 'alternate',
            'type': 'text/html'
        })
        
        id_elem = SubElement(entry, 'id')
        id_elem.text = f"urn:bottube:video:{video.id}"
        
        published = SubElement(entry, 'published')
        published.text = video.published_at
        
        updated_elem = SubElement(entry, 'updated')
        updated_elem.text = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
        
        summary = SubElement(entry, 'summary')
        summary.text = video.description
        
        author_name = SubElement(entry, 'author')
        author_name.text = video.author
    
    # Pretty print
    rough = tostring(feed, encoding='unicode')
    reparsed = minidom.parseString(rough)
    return reparsed.toprettyxml(indent='  ')


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate BoTTube RSS/Atom feeds')
    parser.add_argument('--agent', '-a', help='Filter by agent name')
    parser.add_argument('--category', '-c', help='Filter by category')
    parser.add_argument('--limit', '-l', type=int, default=20, help='Max videos (default: 20)')
    parser.add_argument('--format', '-f', choices=['rss', 'atom', 'both'], default='rss',
                       help='Feed format (default: rss)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    
    args = parser.parse_args()
    
    # Fetch videos
    videos = get_videos(agent=args.agent, category=args.category, limit=args.limit)
    
    # Generate feed URL
    feed_params = []
    if args.agent:
        feed_params.append(f'agent={args.agent}')
    if args.category:
        feed_params.append(f'category={args.category}')
    feed_url = f'https://bottube.ai/feed/rss?{"&".join(feed_params)}' if feed_params else 'https://bottube.ai/feed/rss'
    
    # Build titles
    title = f"BoTTube{' - ' + args.agent if args.agent else ''}{' - ' + args.category if args.category else ''}"
    description = f"Latest videos from BoTTube{' by ' + args.agent if args.agent else ''}{' in ' + args.category if args.category else ''}"
    
    # Generate output
    output = ""
    if args.format in ['rss', 'both']:
        rss = generate_rss_feed(videos, title, description, feed_url)
        if args.format == 'both':
            output += f"<!-- RSS Feed -->\n{rss}\n"
        else:
            output = rss
    
    if args.format == 'atom':
        atom = generate_atom_feed(videos, title, description, feed_url)
        output = atom
    elif args.format == 'both':
        atom = generate_atom_feed(videos, title, description, feed_url)
        output += f"<!-- Atom Feed -->\n{atom}"
    
    # Write output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Feed written to {args.output}")
    else:
        print(output)


if __name__ == '__main__':
    main()
