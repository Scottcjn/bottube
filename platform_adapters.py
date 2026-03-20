import requests
import time
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from urllib.parse import urlencode
import hashlib
import hmac
import base64

@dataclass
class VideoContent:
    video_path: str
    title: str
    description: str
    tags: List[str]
    thumbnail_path: Optional[str] = None
    duration: Optional[int] = None

@dataclass
class PostResult:
    success: bool
    platform: str
    post_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_after: Optional[int] = None

class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests = []

    def wait_if_needed(self):
        now = time.time()
        self.requests = [req_time for req_time in self.requests if now - req_time < 60]

        if len(self.requests) >= self.requests_per_minute:
            sleep_time = 60 - (now - self.requests[0])
            if sleep_time > 0:
                time.sleep(sleep_time)

        self.requests.append(now)

class PlatformAdapter(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.rate_limiter = RateLimiter(config.get('rate_limit', 60))
        self.logger = logging.getLogger(f"{self.__class__.__name__}")

    @abstractmethod
    def authenticate(self) -> bool:
        pass

    @abstractmethod
    def format_content(self, content: VideoContent) -> Dict[str, Any]:
        pass

    @abstractmethod
    def post_content(self, formatted_content: Dict[str, Any]) -> PostResult:
        pass

    def add_bottube_attribution(self, description: str, video_id: str) -> str:
        attribution = f"\n\n🎥 Watch on BoTTube: https://bottube.ai/video/{video_id}\n#BoTTube #AI"
        return description + attribution

class YouTubeShortsAdapter(PlatformAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key')
        self.client_id = config.get('client_id')
        self.client_secret = config.get('client_secret')
        self.access_token = None
        self.refresh_token = config.get('refresh_token')

    def authenticate(self) -> bool:
        if not self.refresh_token:
            self.logger.error("No refresh token provided")
            return False

        try:
            response = requests.post('https://oauth2.googleapis.com/token', data={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': self.refresh_token,
                'grant_type': 'refresh_token'
            })

            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                return True
            else:
                self.logger.error(f"YouTube auth failed: {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"YouTube authentication error: {e}")
            return False

    def format_content(self, content: VideoContent) -> Dict[str, Any]:
        title = content.title[:100] if len(content.title) > 100 else content.title
        description = self.add_bottube_attribution(content.description[:5000], "")

        return {
            'snippet': {
                'title': title,
                'description': description,
                'tags': content.tags[:500],
                'categoryId': '24'  # Entertainment
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False
            }
        }

    def post_content(self, formatted_content: Dict[str, Any]) -> PostResult:
        if not self.access_token and not self.authenticate():
            return PostResult(False, 'youtube_shorts', error_message='Authentication failed')

        self.rate_limiter.wait_if_needed()

        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }

            response = requests.post(
                'https://www.googleapis.com/upload/youtube/v3/videos',
                headers=headers,
                json=formatted_content,
                params={'part': 'snippet,status'}
            )

            if response.status_code == 200:
                video_data = response.json()
                return PostResult(True, 'youtube_shorts', post_id=video_data.get('id'))
            else:
                return PostResult(False, 'youtube_shorts', error_message=response.text)

        except Exception as e:
            self.logger.error(f"YouTube Shorts posting error: {e}")
            return PostResult(False, 'youtube_shorts', error_message=str(e))

class TikTokAdapter(PlatformAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client_key = config.get('client_key')
        self.client_secret = config.get('client_secret')
        self.access_token = config.get('access_token')
        self.base_url = 'https://open-api.tiktok.com'

    def authenticate(self) -> bool:
        return bool(self.access_token and self.client_key)

    def format_content(self, content: VideoContent) -> Dict[str, Any]:
        description = self.add_bottube_attribution(content.description, "")

        return {
            'video': {
                'video_url': content.video_path
            },
            'post_info': {
                'title': content.title[:150],
                'description': description[:2200],
                'privacy_level': 'PUBLIC_TO_EVERYONE',
                'disable_duet': False,
                'disable_comment': False,
                'disable_stitch': False,
                'video_cover_timestamp_ms': 1000
            },
            'source_info': {
                'source': 'PULL_FROM_URL'
            }
        }

    def post_content(self, formatted_content: Dict[str, Any]) -> PostResult:
        if not self.authenticate():
            return PostResult(False, 'tiktok', error_message='Authentication failed')

        self.rate_limiter.wait_if_needed()

        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }

            response = requests.post(
                f'{self.base_url}/v2/post/publish/video/init/',
                headers=headers,
                json=formatted_content
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('error', {}).get('code') == 'ok':
                    return PostResult(True, 'tiktok', post_id=result.get('data', {}).get('publish_id'))
                else:
                    return PostResult(False, 'tiktok', error_message=result.get('error', {}).get('message'))
            else:
                return PostResult(False, 'tiktok', error_message=response.text)

        except Exception as e:
            self.logger.error(f"TikTok posting error: {e}")
            return PostResult(False, 'tiktok', error_message=str(e))

class InstagramReelsAdapter(PlatformAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.access_token = config.get('access_token')
        self.page_id = config.get('page_id')
        self.base_url = 'https://graph.facebook.com/v18.0'

    def authenticate(self) -> bool:
        if not self.access_token:
            return False

        try:
            response = requests.get(f'{self.base_url}/me', params={'access_token': self.access_token})
            return response.status_code == 200
        except:
            return False

    def format_content(self, content: VideoContent) -> Dict[str, Any]:
        caption = f"{content.title}\n\n{content.description}"
        caption = self.add_bottube_attribution(caption, "")

        return {
            'video_url': content.video_path,
            'caption': caption[:2200],
            'media_type': 'REELS'
        }

    def post_content(self, formatted_content: Dict[str, Any]) -> PostResult:
        if not self.authenticate():
            return PostResult(False, 'instagram_reels', error_message='Authentication failed')

        self.rate_limiter.wait_if_needed()

        try:
            # Create media container
            container_params = {
                'video_url': formatted_content['video_url'],
                'caption': formatted_content['caption'],
                'media_type': formatted_content['media_type'],
                'access_token': self.access_token
            }

            container_response = requests.post(
                f'{self.base_url}/{self.page_id}/media',
                data=container_params
            )

            if container_response.status_code != 200:
                return PostResult(False, 'instagram_reels', error_message=container_response.text)

            container_id = container_response.json().get('id')

            # Publish media
            publish_response = requests.post(
                f'{self.base_url}/{self.page_id}/media_publish',
                data={
                    'creation_id': container_id,
                    'access_token': self.access_token
                }
            )

            if publish_response.status_code == 200:
                result = publish_response.json()
                return PostResult(True, 'instagram_reels', post_id=result.get('id'))
            else:
                return PostResult(False, 'instagram_reels', error_message=publish_response.text)

        except Exception as e:
            self.logger.error(f"Instagram Reels posting error: {e}")
            return PostResult(False, 'instagram_reels', error_message=str(e))

class XTwitterAdapter(PlatformAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.consumer_key = config.get('consumer_key')
        self.consumer_secret = config.get('consumer_secret')
        self.access_token = config.get('access_token')
        self.access_token_secret = config.get('access_token_secret')
        self.base_url = 'https://upload.twitter.com/1.1'

    def authenticate(self) -> bool:
        return all([self.consumer_key, self.consumer_secret, self.access_token, self.access_token_secret])

    def _get_oauth_header(self, method: str, url: str, params: Dict = None) -> str:
        oauth_params = {
            'oauth_consumer_key': self.consumer_key,
            'oauth_token': self.access_token,
            'oauth_signature_method': 'HMAC-SHA1',
            'oauth_timestamp': str(int(time.time())),
            'oauth_nonce': hashlib.md5(str(time.time()).encode()).hexdigest(),
            'oauth_version': '1.0'
        }

        if params:
            oauth_params.update(params)

        param_string = '&'.join([f'{k}={v}' for k, v in sorted(oauth_params.items())])
        base_string = f'{method}&{requests.utils.quote(url, safe="")}&{requests.utils.quote(param_string, safe="")}'

        signing_key = f'{requests.utils.quote(self.consumer_secret, safe="")}&{requests.utils.quote(self.access_token_secret, safe="")}'
        signature = base64.b64encode(hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()).decode()

        oauth_params['oauth_signature'] = signature

        auth_header = 'OAuth ' + ', '.join([f'{k}="{requests.utils.quote(str(v), safe="")}"' for k, v in oauth_params.items()])
        return auth_header

    def format_content(self, content: VideoContent) -> Dict[str, Any]:
        tweet_text = f"{content.title[:200]}\n\n{self.add_bottube_attribution('', '')}"

        return {
            'status': tweet_text[:280],
            'video_path': content.video_path
        }

    def post_content(self, formatted_content: Dict[str, Any]) -> PostResult:
        if not self.authenticate():
            return PostResult(False, 'x_twitter', error_message='Authentication failed')

        self.rate_limiter.wait_if_needed()

        try:
            # Upload media first
            with open(formatted_content['video_path'], 'rb') as video_file:
                video_data = video_file.read()

            upload_url = f'{self.base_url}/media/upload.json'
            headers = {'Authorization': self._get_oauth_header('POST', upload_url)}

            files = {'media': video_data}
            upload_response = requests.post(upload_url, headers=headers, files=files)

            if upload_response.status_code != 200:
                return PostResult(False, 'x_twitter', error_message=upload_response.text)

            media_id = upload_response.json().get('media_id_string')

            # Post tweet with media
            tweet_url = 'https://api.twitter.com/1.1/statuses/update.json'
            tweet_params = {
                'status': formatted_content['status'],
                'media_ids': media_id
            }

            tweet_headers = {'Authorization': self._get_oauth_header('POST', tweet_url, tweet_params)}
            tweet_response = requests.post(tweet_url, headers=tweet_headers, data=tweet_params)

            if tweet_response.status_code == 200:
                tweet_data = tweet_response.json()
                return PostResult(True, 'x_twitter', post_id=tweet_data.get('id_str'))
            else:
                return PostResult(False, 'x_twitter', error_message=tweet_response.text)

        except Exception as e:
            self.logger.error(f"X/Twitter posting error: {e}")
            return PostResult(False, 'x_twitter', error_message=str(e))

class RedditAdapter(PlatformAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client_id = config.get('client_id')
        self.client_secret = config.get('client_secret')
        self.username = config.get('username')
        self.password = config.get('password')
        self.user_agent = config.get('user_agent', 'BoTTube Syndication Bot v1.0')
        self.access_token = None
        self.subreddit = config.get('subreddit', 'videos')

    def authenticate(self) -> bool:
        try:
            auth = requests.auth.HTTPBasicAuth(self.client_id, self.client_secret)
            data = {
                'grant_type': 'password',
                'username': self.username,
                'password': self.password
            }
            headers = {'User-Agent': self.user_agent}

            response = requests.post(
                'https://www.reddit.com/api/v1/access_token',
                auth=auth,
                data=data,
                headers=headers
            )

            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                return True
            else:
                self.logger.error(f"Reddit auth failed: {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Reddit authentication error: {e}")
            return False

    def format_content(self, content: VideoContent) -> Dict[str, Any]:
        title = content.title[:300]
        description = self.add_bottube_attribution(content.description, "")

        return {
            'sr': self.subreddit,
            'kind': 'link',
            'title': title,
            'text': description,
            'url': content.video_path,
            'flair_id': None
        }

    def post_content(self, formatted_content: Dict[str, Any]) -> PostResult:
        if not self.access_token and not self.authenticate():
            return PostResult(False, 'reddit', error_message='Authentication failed')

        self.rate_limiter.wait_if_needed()

        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'User-Agent': self.user_agent,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(
                'https://oauth.reddit.com/api/submit',
                headers=headers,
                data=formatted_content
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return PostResult(True, 'reddit', post_id=result.get('json', {}).get('data', {}).get('name'))
                else:
                    errors = result.get('json', {}).get('errors', [])
                    error_msg = str(errors[0]) if errors else 'Unknown error'
                    return PostResult(False, 'reddit', error_message=error_msg)
            else:
                return PostResult(False, 'reddit', error_message=response.text)

        except Exception as e:
            self.logger.error(f"Reddit posting error: {e}")
            return PostResult(False, 'reddit', error_message=str(e))

def create_platform_adapter(platform: str, config: Dict[str, Any]) -> Optional[PlatformAdapter]:
    adapters = {
        'youtube_shorts': YouTubeShortsAdapter,
        'tiktok': TikTokAdapter,
        'instagram_reels': InstagramReelsAdapter,
        'x_twitter': XTwitterAdapter,
        'reddit': RedditAdapter
    }

    adapter_class = adapters.get(platform.lower())
    if adapter_class:
        return adapter_class(config)
    else:
        logging.warning(f"Unknown platform: {platform}")
        return None
