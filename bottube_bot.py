#!/usr/bin/env python3
"""
BoTTube Upload Bot
Bounty #211 - 10 RTC

SPDX-License-Identifier: MIT
"""

import os
import sys
import argparse
import logging
import requests
from pathlib import Path

BOTUBE_API_KEY = os.getenv('BOTUBE_API_KEY')
BOTUBE_API_URL = os.getenv('BOTUBE_API_URL', 'https://api.bottube.io/v1')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('bottube_bot')

class BoTTubeBot:
    """BoTTube video upload bot with CLI interface."""
    
    def __init__(self, api_key=None, api_url=None):
        self.api_key = api_key or BOTUBE_API_KEY
        self.api_url = api_url or BOTUBE_API_URL
        if not self.api_key:
            raise ValueError("API key required. Set BOTUBE_API_KEY env var.")
    
    def upload_video(self, video_path, title, description="", tags=None):
        """Upload a video to BoTTube."""
        url = f"{self.api_url}/videos"
        
        headers = {
            'Authorization': f'Bearer {self.api_key}'
            # Note: Do NOT set Content-Type here, requests sets it automatically for multipart
        }
        
        with open(video_path, 'rb') as f:
            files = {'video': f}
            data = {'title': title}
            if description:
                data['description'] = description
            if tags:
                data['tags'] = ','.join(tags)
            
            logger.info(f"Uploading {video_path}...")
            response = requests.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()
            
        result = response.json()
        logger.info(f"Upload successful: {result.get('id', 'unknown')}")
        return result
    
    def search(self, query, limit=10):
        """Search videos."""
        url = f"{self.api_url}/videos"
        headers = {'Authorization': f'Bearer {self.api_key}'}
        params = {'q': query, 'limit': limit}
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

def main():
    parser = argparse.ArgumentParser(description='BoTTube Upload Bot')
    parser.add_argument('--upload', '-u', help='Video file to upload')
    parser.add_argument('--title', '-t', help='Video title')
    parser.add_argument('--description', '-d', default='', help='Video description')
    parser.add_argument('--tags', help='Comma-separated tags')
    parser.add_argument('--search', '-s', help='Search query')
    
    args = parser.parse_args()
    
    bot = BoTTubeBot()
    
    if args.upload:
        if not args.title:
            print("Error: --title required for upload")
            sys.exit(1)
        tags = args.tags.split(',') if args.tags else None
        result = bot.upload_video(args.upload, args.title, args.description, tags)
        print(f"Uploaded: {result}")
    elif args.search:
        results = bot.search(args.search)
        print(f"Search results: {results}")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
