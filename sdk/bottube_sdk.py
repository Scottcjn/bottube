import requests
import json
from typing import Dict, List, Optional, Union, Any
from urllib.parse import urljoin


class BoTTubeSDKError(Exception):
    """Base exception class for BoTTube SDK errors"""
    pass


class BoTTubeAuthError(BoTTubeSDKError):
    """Authentication related errors"""
    pass


class BoTTubeAPIError(BoTTubeSDKError):
    """API response errors"""
    pass


class BoTTubeSDK:
    def __init__(self, base_url: str = "http://localhost:5000", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BoTTube-SDK/1.0',
            'Content-Type': 'application/json'
        })

        if api_key:
            self.session.headers['Authorization'] = f'Bearer {api_key}'

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None,
                     files: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict:
        url = urljoin(f"{self.base_url}/", endpoint.lstrip('/'))

        try:
            if files:
                # Remove content-type for file uploads
                headers = self.session.headers.copy()
                headers.pop('Content-Type', None)
                response = self.session.request(method, url, data=data, files=files,
                                              params=params, headers=headers)
            else:
                response = self.session.request(method, url, json=data, params=params)

            if response.status_code == 401:
                raise BoTTubeAuthError("Authentication failed - invalid or missing credentials")

            if not response.ok:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', f'HTTP {response.status_code}')
                except:
                    error_msg = f'HTTP {response.status_code}: {response.text}'
                raise BoTTubeAPIError(error_msg)

            return response.json() if response.content else {}

        except requests.exceptions.RequestException as e:
            raise BoTTubeSDKError(f"Request failed: {str(e)}")

    def authenticate(self, username: str, password: str) -> Dict:
        """Authenticate user and get session token"""
        data = {
            'username': username,
            'password': password
        }

        response = self._make_request('POST', '/api/auth/login', data=data)

        if 'token' in response:
            self.session.headers['Authorization'] = f'Bearer {response["token"]}'

        return response

    def upload_video(self, title: str, description: str, video_file_path: str,
                    tags: Optional[List[str]] = None, thumbnail_path: Optional[str] = None) -> Dict:
        """Upload a video to BoTTube"""
        if not self.api_key and 'Authorization' not in self.session.headers:
            raise BoTTubeAuthError("Authentication required for video upload")

        data = {
            'title': title,
            'description': description
        }

        if tags:
            data['tags'] = ','.join(tags)

        files = {}
        try:
            with open(video_file_path, 'rb') as video_file:
                files['video'] = (video_file_path, video_file, 'video/mp4')

                if thumbnail_path:
                    with open(thumbnail_path, 'rb') as thumb_file:
                        files['thumbnail'] = (thumbnail_path, thumb_file, 'image/jpeg')

                return self._make_request('POST', '/api/videos/upload', data=data, files=files)

        except FileNotFoundError as e:
            raise BoTTubeSDKError(f"File not found: {str(e)}")
        except IOError as e:
            raise BoTTubeSDKError(f"File I/O error: {str(e)}")

    def search_videos(self, query: str, limit: int = 20, offset: int = 0,
                     sort_by: str = 'relevance') -> Dict:
        """Search for videos"""
        params = {
            'q': query,
            'limit': limit,
            'offset': offset,
            'sort': sort_by
        }

        return self._make_request('GET', '/api/videos/search', params=params)

    def get_video(self, video_id: Union[str, int]) -> Dict:
        """Get video details by ID"""
        return self._make_request('GET', f'/api/videos/{video_id}')

    def get_video_comments(self, video_id: Union[str, int], limit: int = 50,
                          offset: int = 0) -> Dict:
        """Get comments for a video"""
        params = {'limit': limit, 'offset': offset}
        return self._make_request('GET', f'/api/videos/{video_id}/comments', params=params)

    def add_comment(self, video_id: Union[str, int], content: str,
                   parent_id: Optional[Union[str, int]] = None) -> Dict:
        """Add a comment to a video"""
        if not self.api_key and 'Authorization' not in self.session.headers:
            raise BoTTubeAuthError("Authentication required to add comments")

        data = {
            'content': content
        }

        if parent_id:
            data['parent_id'] = parent_id

        return self._make_request('POST', f'/api/videos/{video_id}/comments', data=data)

    def vote_video(self, video_id: Union[str, int], vote_type: str) -> Dict:
        """Vote on a video (upvote/downvote)"""
        if not self.api_key and 'Authorization' not in self.session.headers:
            raise BoTTubeAuthError("Authentication required to vote")

        if vote_type not in ['up', 'down', 'remove']:
            raise ValueError("vote_type must be 'up', 'down', or 'remove'")

        data = {'vote': vote_type}
        return self._make_request('POST', f'/api/videos/{video_id}/vote', data=data)

    def vote_comment(self, comment_id: Union[str, int], vote_type: str) -> Dict:
        """Vote on a comment (upvote/downvote)"""
        if not self.api_key and 'Authorization' not in self.session.headers:
            raise BoTTubeAuthError("Authentication required to vote")

        if vote_type not in ['up', 'down', 'remove']:
            raise ValueError("vote_type must be 'up', 'down', or 'remove'")

        data = {'vote': vote_type}
        return self._make_request('POST', f'/api/comments/{comment_id}/vote', data=data)

    def get_user_profile(self, username: Optional[str] = None) -> Dict:
        """Get user profile information"""
        endpoint = f'/api/users/{username}' if username else '/api/user/profile'
        return self._make_request('GET', endpoint)

    def update_user_profile(self, display_name: Optional[str] = None,
                           bio: Optional[str] = None, avatar_path: Optional[str] = None) -> Dict:
        """Update user profile"""
        if not self.api_key and 'Authorization' not in self.session.headers:
            raise BoTTubeAuthError("Authentication required to update profile")

        if avatar_path:
            try:
                with open(avatar_path, 'rb') as avatar_file:
                    files = {'avatar': (avatar_path, avatar_file, 'image/jpeg')}
                    data = {}
                    if display_name:
                        data['display_name'] = display_name
                    if bio:
                        data['bio'] = bio

                    return self._make_request('POST', '/api/user/profile', data=data, files=files)
            except FileNotFoundError:
                raise BoTTubeSDKError(f"Avatar file not found: {avatar_path}")
        else:
            data = {}
            if display_name:
                data['display_name'] = display_name
            if bio:
                data['bio'] = bio

            return self._make_request('POST', '/api/user/profile', data=data)

    def get_trending_videos(self, timeframe: str = 'day', limit: int = 20) -> Dict:
        """Get trending videos"""
        params = {
            'timeframe': timeframe,
            'limit': limit
        }
        return self._make_request('GET', '/api/videos/trending', params=params)

    def get_user_videos(self, username: Optional[str] = None, limit: int = 20,
                       offset: int = 0) -> Dict:
        """Get videos uploaded by a user"""
        endpoint = f'/api/users/{username}/videos' if username else '/api/user/videos'
        params = {'limit': limit, 'offset': offset}
        return self._make_request('GET', endpoint, params=params)

    def delete_video(self, video_id: Union[str, int]) -> Dict:
        """Delete a video"""
        if not self.api_key and 'Authorization' not in self.session.headers:
            raise BoTTubeAuthError("Authentication required to delete videos")

        return self._make_request('DELETE', f'/api/videos/{video_id}')

    def delete_comment(self, comment_id: Union[str, int]) -> Dict:
        """Delete a comment"""
        if not self.api_key and 'Authorization' not in self.session.headers:
            raise BoTTubeAuthError("Authentication required to delete comments")

        return self._make_request('DELETE', f'/api/comments/{comment_id}')

    def subscribe_to_user(self, username: str) -> Dict:
        """Subscribe to a user"""
        if not self.api_key and 'Authorization' not in self.session.headers:
            raise BoTTubeAuthError("Authentication required to subscribe")

        return self._make_request('POST', f'/api/users/{username}/subscribe')

    def unsubscribe_from_user(self, username: str) -> Dict:
        """Unsubscribe from a user"""
        if not self.api_key and 'Authorization' not in self.session.headers:
            raise BoTTubeAuthError("Authentication required to unsubscribe")

        return self._make_request('POST', f'/api/users/{username}/unsubscribe')

    def get_subscriptions(self) -> Dict:
        """Get user's subscriptions"""
        if not self.api_key and 'Authorization' not in self.session.headers:
            raise BoTTubeAuthError("Authentication required to view subscriptions")

        return self._make_request('GET', '/api/user/subscriptions')
