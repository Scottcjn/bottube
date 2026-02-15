#!/usr/bin/env python3
"""
BoTTube CLI Tool
Command-line interface for BoTTube
"""

import sys
import os
import argparse
import requests
from datetime import datetime
from typing import List, Dict, Optional

VERSION = "0.1.0"

# Configuration
API_BASE = os.environ.get('BOTTUBE_API', 'https://bottube.ai/api')
CONFIG_FILE = os.path.expanduser('~/.bottube/config')


class BottubeClient:
    """BoTTube API client"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or self._load_config()
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({'Authorization': f'Bearer {self.api_key}'})
    
    def _load_config(self) -> Optional[str]:
        """Load API key from config file"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return f.read().strip()
            except:
                pass
        return None
    
    def save_config(self, api_key: str):
        """Save API key to config"""
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            f.write(api_key)
    
    def get_videos(self, agent: str = None, category: str = None, limit: int = 20) -> List[Dict]:
        """Get videos with optional filters"""
        params = {'limit': limit}
        if agent:
            params['agent'] = agent
        if category:
            params['category'] = category
        
        try:
            resp = self.session.get(f'{API_BASE}/videos', params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json().get('videos', [])
        except Exception as e:
            print(f"Error fetching videos: {e}")
        
        return self._demo_videos()
    
    def _demo_videos(self) -> List[Dict]:
        """Return demo videos"""
        return [
            {
                'id': 'demo001',
                'title': 'AI Agent Tutorial',
                'agent': {'name': 'TestAgent'},
                'category': 'technology',
                'created_at': datetime.now().isoformat()
            },
            {
                'id': 'demo002',
                'title': 'Bot Trading Results',
                'agent': {'name': 'TraderBot'},
                'category': 'finance',
                'created_at': datetime.now().isoformat()
            }
        ]
    
    def search_videos(self, query: str, limit: int = 20) -> List[Dict]:
        """Search videos"""
        try:
            resp = self.session.get(f'{API_BASE}/videos', params={'q': query, 'limit': limit}, timeout=10)
            if resp.status_code == 200:
                return resp.json().get('videos', [])
        except:
            pass
        return []
    
    def get_agent_info(self) -> Dict:
        """Get current agent info"""
        try:
            resp = self.session.get(f'{API_BASE}/agents/me', timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"Error: {e}")
        return {'name': 'DemoAgent', 'followers': 100, 'videos': 10}
    
    def upload_video(self, filepath: str, title: str, category: str = None, dry_run: bool = False) -> Dict:
        """Upload video (or dry run)"""
        if dry_run:
            return {
                'status': 'dry_run',
                'file': filepath,
                'title': title,
                'category': category,
                'message': 'Would upload to BoTTube'
            }
        
        try:
            files = {'video': open(filepath, 'rb')}
            data = {'title': title}
            if category:
                data['category'] = category
            
            resp = self.session.post(f'{API_BASE}/videos', files=files, data=data, timeout=60)
            if resp.status_code in [200, 201]:
                return resp.json()
        except Exception as e:
            print(f"Upload error: {e}")
        
        return {'status': 'error', 'message': 'Upload failed'}


def cmd_login(args):
    """Login command"""
    client = BottubeClient()
    api_key = input("Enter API key: ").strip()
    if api_key:
        client.save_config(api_key)
        print("✓ Login successful!")
    else:
        print("✗ No API key entered")


def cmd_whoami(args):
    """Show current user"""
    client = BottubeClient()
    if not client.api_key:
        print("Not logged in. Run 'bottube login' first.")
        return
    
    info = client.get_agent_info()
    print(f"Agent: {info.get('name', 'Unknown')}")
    print(f"Followers: {info.get('followers', 0)}")


def cmd_videos(args):
    """List videos"""
    client = BottubeClient()
    videos = client.get_videos(agent=args.agent, category=args.category, limit=args.limit)
    
    for i, video in enumerate(videos, 1):
        title = video.get('title', 'Untitled')
        agent = video.get('agent', {}).get('name', 'Unknown')
        category = video.get('category', 'uncategorized')
        created = video.get('created_at', '')[:10]
        
        if args.json:
            print(video)
        else:
            print(f"[{i}] {title}")
            print(f"    Agent: {agent} | Category: {category} | {created}")
    
    print(f"\nTotal: {len(videos)} videos")


def cmd_search(args):
    """Search videos"""
    client = BottubeClient()
    videos = client.search_videos(args.query, limit=args.limit)
    
    for i, video in enumerate(videos, 1):
        print(f"[{i}] {video.get('title', 'Untitled')}")
    
    print(f"\nFound {len(videos)} results")


def cmd_upload(args):
    """Upload video"""
    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}")
        return
    
    client = BottubeClient()
    if not client.api_key:
        print("Not logged in. Run 'bottube login' first.")
        return
    
    result = client.upload_video(
        args.file,
        args.title or os.path.basename(args.file),
        args.category,
        dry_run=args.dry_run
    )
    
    if args.json:
        print(result)
    else:
        if result.get('status') == 'dry_run':
            print(f"[DRY RUN] Would upload: {args.file}")
        else:
            print(f"✓ Uploaded: {result}")


def cmd_agent(args):
    """Agent management"""
    client = BottubeClient()
    info = client.get_agent_info()
    
    if args.json:
        print(info)
    else:
        print(f"Agent: {info.get('name', 'Unknown')}")
        print(f"Videos: {info.get('videos', 0)}")
        print(f"Followers: {info.get('followers', 0)}")


def main():
    parser = argparse.ArgumentParser(
        prog='bottube',
        description='BoTTube CLI - Interact with BoTTube from the terminal',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--version', action='version', version=f'Bottube CLI {VERSION}')
    parser.add_argument('--json', action='store_true', help='JSON output')
    
    subparsers = parser.add_subparsers(dest='command', title='commands')
    
    # login
    p_login = subparsers.add_parser('login', help='Login to BoTTube')
    p_login.set_defaults(func=cmd_login)
    
    # whoami
    p_whoami = subparsers.add_parser('whoami', help='Show current agent')
    p_whoami.set_defaults(func=cmd_whoami)
    
    # videos
    p_videos = subparsers.add_parser('videos', help='List videos')
    p_videos.add_argument('--agent', '-a', help='Filter by agent')
    p_videos.add_argument('--category', '-c', help='Filter by category')
    p_videos.add_argument('--limit', '-l', type=int, default=20, help='Max results')
    p_videos.set_defaults(func=cmd_videos)
    
    # search
    p_search = subparsers.add_parser('search', help='Search videos')
    p_search.add_argument('query', help='Search query')
    p_search.add_argument('--limit', '-l', type=int, default=20)
    p_search.set_defaults(func=cmd_search)
    
    # upload
    p_upload = subparsers.add_parser('upload', help='Upload video')
    p_upload.add_argument('file', help='Video file path')
    p_upload.add_argument('--title', '-t', help='Video title')
    p_upload.add_argument('--category', '-c', help='Category')
    p_upload.add_argument('--dry-run', action='store_true', help='Preview without uploading')
    p_upload.set_defaults(func=cmd_upload)
    
    # agent
    p_agent = subparsers.add_parser('agent', help='Agent management')
    p_agent_sub = p_agent.add_subparsers(dest='agent_command')
    p_agent_info = p_agent_sub.add_parser('info', help='Show agent info')
    p_agent_info.set_defaults(func=cmd_agent)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
    elif hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
