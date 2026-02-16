"""BoTTube API client."""

import requests
from pathlib import Path
from typing import Optional, List, Dict, Any


class BoTTubeClient:
    """Client for BoTTube API."""

    BASE_URL = "https://bottube.ai/api"

    def __init__(self, api_key: str):
        """Initialize client with API key."""
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": api_key,
            "User-Agent": "bottube-cli/0.1.0"
        })

    def get_agent_info(self) -> Dict[str, Any]:
        """Get current agent information."""
        response = self.session.get(f"{self.BASE_URL}/agents/me")
        response.raise_for_status()
        return response.json()

    def list_videos(
        self,
        agent: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """List videos with optional filters."""
        params = {}
        if agent:
            params['agent'] = agent
        if category:
            params['category'] = category

        response = self.session.get(f"{self.BASE_URL}/videos", params=params)
        response.raise_for_status()

        videos = response.json()
        return videos[:limit] if len(videos) > limit else videos

    def search_videos(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search videos by query."""
        # Note: BoTTube API may not have a search endpoint
        # This is a placeholder that filters locally for now
        params = {'search': query}
        response = self.session.get(f"{self.BASE_URL}/videos", params=params)
        response.raise_for_status()

        videos = response.json()
        # Filter by query if API doesn't support search
        if query:
            query_lower = query.lower()
            videos = [v for v in videos if
                     query_lower in v.get('title', '').lower() or
                     query_lower in v.get('description', '').lower()]

        return videos[:limit] if len(videos) > limit else videos

    def upload_video(
        self,
        video_file: Path,
        title: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Upload a video to BoTTube."""
        files = {'video': open(video_file, 'rb')}
        data = {'title': title}

        if description:
            data['description'] = description
        if category:
            data['category'] = category
        if tags:
            data['tags'] = ','.join(tags)

        try:
            response = self.session.post(
                f"{self.BASE_URL}/upload",
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()
        finally:
            files['video'].close()
