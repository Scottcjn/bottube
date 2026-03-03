"""
BoTTube Python SDK Client
"""

import os
import logging
import requests

class BoTubeClient:
    """BoTube API client."""
    
    DEFAULT_BASE_URL = 'https://api.bottube.io/v1'
    
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or os.getenv('BOTUBE_API_KEY')
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        })
        self.logger = logging.getLogger(__name__)
    
    def upload(self, video_path, title, description='', tags=None):
        """Upload a video."""
        url = f"{self.base_url}/videos"
        with open(video_path, 'rb') as f:
            files = {'video': f}
            data = {'title': title, 'description': description}
            if tags:
                data['tags'] = ','.join(tags)
            response = self.session.post(url, files=files, data=data)
            response.raise_for_status()
        return response.json()
    
    def search(self, query, limit=10):
        """Search videos."""
        url = f"{self.base_url}/search"
        params = {'q': query, 'limit': limit}
        response = self.session.get(url, params=params)
        return response.json()
    
    def get_video(self, video_id):
        """Get video details."""
        url = f"{self.base_url}/videos/{video_id}"
        response = self.session.get(url)
        return response.json()
