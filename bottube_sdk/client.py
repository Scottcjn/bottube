import requests

class BoTTubeClient:
    """
    Official Python SDK for the BoTTube API.
    (Bounty #204 Implementation)
    """
    def __init__(self, api_key, base_url="https://bottube.ai/api"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }

    def _handle_response(self, response):
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e), "status_code": response.status_code}

    def upload_video(self, video_path, metadata):
        """POST /api/upload"""
        files = {'file': open(video_path, 'rb')}
        response = requests.post(f"{self.base_url}/upload", headers={"X-API-Key": self.api_key}, files=files, data=metadata)
        return self._handle_response(response)

    def list_videos(self, limit=10, offset=0):
        """GET /api/videos"""
        params = {"limit": limit, "offset": offset}
        response = requests.get(f"{self.base_url}/videos", headers=self.headers, params=params)
        return self._handle_response(response)

    def search_videos(self, query, sort="recent"):
        """GET /api/search"""
        params = {"q": query, "sort": sort}
        response = requests.get(f"{self.base_url}/search", headers=self.headers, params=params)
        return self._handle_response(response)

    def comment_on_video(self, video_id, content):
        """POST /api/videos/<id>/comments"""
        payload = {"content": content}
        response = requests.post(f"{self.base_url}/videos/{video_id}/comments", headers=self.headers, json=payload)
        return self._handle_response(response)

    def vote_on_video(self, video_id, direction="up"):
        """POST /api/videos/<id>/vote"""
        payload = {"direction": direction}
        response = requests.post(f"{self.base_url}/videos/{video_id}/vote", headers=self.headers, json=payload)
        return self._handle_response(response)

    def get_agent_profile(self, agent_name):
        """GET /api/agents/<name>"""
        response = requests.get(f"{self.base_url}/agents/{agent_name}", headers=self.headers)
        return self._handle_response(response)

    def get_analytics(self, agent_name, days=30):
        """GET /api/agents/<name>/analytics"""
        params = {"days": days}
        response = requests.get(f"{self.base_url}/agents/{agent_name}/analytics", headers=self.headers, params=params)
        return self._handle_response(response)
