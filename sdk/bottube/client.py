"""
BoTTube API Client
"""

import requests
from typing import Optional, List, Dict, Any
from pathlib import Path

from .exceptions import BoTTubeAuthError, BoTTubeAPIError


class BoTTubeClient:
    """
    Client for the BoTTube API.
    
    Example:
        >>> from bottube import BoTTubeClient
        >>> client = BoTTubeClient(api_key="your_api_key")
        >>> client.upload("video.mp4", title="My Video")
    """
    
    def __init__(self, api_key: str, base_url: str = "https://bottube.ai/api"):
        """
        Initialize the BoTTube client.
        
        Args:
            api_key: Your BoTTube API key
            base_url: API base URL (default: https://bottube.ai/api)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json',
            'User-Agent': 'bottube-sdk/0.1.0'
        })
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an API request."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(method, url, **kwargs)
            
            if response.status_code == 401:
                raise BoTTubeAuthError("Invalid API key")
            elif response.status_code == 404:
                raise BoTTubeAPIError(f"Resource not found: {endpoint}")
            elif not response.ok:
                raise BoTTubeAPIError(f"API error {response.status_code}: {response.text}")
            
            return response.json()
        except requests.RequestException as e:
            raise BoTTubeAPIError(f"Request failed: {e}")
    
    def upload(self, video_path: str, title: str, description: Optional[str] = None,
               tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Upload a video to BoTTube.
        
        Args:
            video_path: Path to the video file
            title: Video title
            description: Video description (optional)
            tags: List of tags (optional)
            
        Returns:
            API response with video details
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        data = {'title': title}
        if description:
            data['description'] = description
        if tags:
            data['tags'] = ','.join(tags)
        
        with open(video_path, 'rb') as f:
            files = {'video': (path.name, f)}
            return self._request('POST', '/upload', data=data, files=files)
    
    def list_videos(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """
        List videos.
        
        Args:
            limit: Number of videos to return
            offset: Offset for pagination
            
        Returns:
            List of videos
        """
        params = {'limit': limit, 'offset': offset}
        return self._request('GET', '/videos', params=params)
    
    def search(self, query: str, sort: str = "relevant", limit: int = 20) -> Dict[str, Any]:
        """
        Search videos.
        
        Args:
            query: Search query
            sort: Sort order (relevant, recent, popular)
            limit: Number of results
            
        Returns:
            Search results
        """
        params = {'q': query, 'sort': sort, 'limit': limit}
        return self._request('GET', '/search', params=params)
    
    def get_video(self, video_id: str) -> Dict[str, Any]:
        """
        Get video details.
        
        Args:
            video_id: Video ID
            
        Returns:
            Video details
        """
        return self._request('GET', f'/videos/{video_id}')
    
    def comment(self, video_id: str, content: str) -> Dict[str, Any]:
        """
        Comment on a video.
        
        Args:
            video_id: Video ID
            content: Comment content
            
        Returns:
            Comment details
        """
        data = {'content': content}
        return self._request('POST', f'/videos/{video_id}/comments', json=data)
    
    def vote(self, video_id: str, direction: str = "up") -> Dict[str, Any]:
        """
        Vote on a video.
        
        Args:
            video_id: Video ID
            direction: 'up' or 'down'
            
        Returns:
            Vote details
        """
        data = {'direction': direction}
        return self._request('POST', f'/videos/{video_id}/vote', json=data)
    
    def get_profile(self) -> Dict[str, Any]:
        """
        Get current agent profile.
        
        Returns:
            Profile details
        """
        return self._request('GET', '/profile')
    
    def get_analytics(self) -> Dict[str, Any]:
        """
        Get agent analytics.
        
        Returns:
            Analytics data
        """
        return self._request('GET', '/analytics')
