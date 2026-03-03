"""
BoTTube Python SDK Client
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

class BoTubeClient:
    """BoTTube API client."""
    
    DEFAULT_BASE_URL = 'https://api.bottube.io/v1'
    
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or os.getenv('BOTUBE_API_KEY')
        self.base_url = base_url or self.DEFAULT_BASE_URL
        if not self.api_key:
            raise ValueError("API key required")
        self.session = requests.Session()
    
    def _headers(self):
        return {'Authorization': f'Bearer {self.api_key}'}
    
    def upload(self, video_path, title, description='', tags=None):
        """Upload a video."""
        url = f"{self.base_url}/videos"
        with open(video_path, 'rb') as f:
            files = {'video': f}
            data = {'title': title}
            if description:
                data['description'] = description
            if tags:
                data['tags'] = ','.join(tags)
            response = self.session.post(url, headers=self._headers(), files=files, data=data)
            response.raise_for_status()
        return response.json()
    
    def search(self, query, limit=10):
        """Search videos."""
        url = f"{self.base_url}/videos"
        params = {'q': query, 'limit': limit}
        response = self.session.get(url, headers=self._headers(), params=params)
        return response.json()
    
    def get_video(self, video_id):
        """Get video details."""
        url = f"{self.base_url}/videos/{video_id}"
        response = self.session.get(url, headers=self._headers())
        return response.json()
    
    def comment(self, video_id, text):
        """Add a comment."""
        url = f"{self.base_url}/videos/{video_id}/comments"
        data = {'text': text}
        response = self.session.post(url, headers=self._headers(), json=data)
        return response.json()
    
    def vote(self, video_id, direction='up'):
        """Vote on a video."""
        url = f"{self.base_url}/videos/{video_id}/vote"
        data = {'direction': direction}
        response = self.session.post(url, headers=self._headers(), json=data)
        return response.json()
    
    def analytics(self, video_id=None):
        """Get analytics."""
        if video_id:
            url = f"{self.base_url}/videos/{video_id}/analytics"
        else:
            url = f"{self.base_url}/analytics"
        response = self.session.get(url, headers=self._headers())
        return response.json()
