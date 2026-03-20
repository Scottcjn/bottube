import requests
import time
import json
import logging
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class DiscordRateLimitError(Exception):
    """Raised when Discord rate limit is hit"""
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after} seconds")

class DiscordWebhookError(Exception):
    """Raised when Discord webhook request fails"""
    pass

class DiscordTransport:
    def __init__(self, webhook_url: str, timeout: int = 30, max_retries: int = 3):
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._validate_webhook_url()

    def _validate_webhook_url(self):
        """Validate Discord webhook URL format"""
        parsed = urlparse(self.webhook_url)
        if not parsed.scheme in ('http', 'https'):
            raise ValueError("Webhook URL must use http or https")
        if 'discord.com' not in parsed.netloc:
            raise ValueError("Webhook URL must be a Discord webhook")
        if '/api/webhooks/' not in parsed.path:
            raise ValueError("Invalid Discord webhook path")

    def _exponential_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay"""
        return min(2 ** attempt + (time.time() % 1), 60)

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Handle Discord API response with proper error handling"""
        if response.status_code == 204:
            return {"status": "success", "message": "Message sent successfully"}

        if response.status_code == 429:
            retry_after = float(response.headers.get('Retry-After', 1))
            raise DiscordRateLimitError(retry_after)

        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_msg = error_data.get('message', f'HTTP {response.status_code}')
            except (json.JSONDecodeError, ValueError):
                error_msg = f'HTTP {response.status_code}: {response.text}'

            raise DiscordWebhookError(f"Discord API error: {error_msg}")

        try:
            return response.json()
        except (json.JSONDecodeError, ValueError):
            return {"status": "success", "raw_response": response.text}

    def _make_request(self, payload: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """Make request to Discord with retry logic"""
        if dry_run:
            logger.info(f"DRY RUN: Would send to Discord: {json.dumps(payload, indent=2)}")
            return {"status": "dry_run", "payload": payload}

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Beacon-Discord-Transport/1.0'
        }

        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                return self._handle_response(response)

            except DiscordRateLimitError as e:
                if attempt < self.max_retries:
                    logger.warning(f"Rate limited, waiting {e.retry_after}s before retry {attempt + 1}/{self.max_retries}")
                    time.sleep(e.retry_after)
                    continue
                raise

            except (requests.RequestException, DiscordWebhookError) as e:
                if attempt < self.max_retries:
                    backoff_time = self._exponential_backoff(attempt)
                    logger.warning(f"Request failed, retrying in {backoff_time}s: {str(e)}")
                    time.sleep(backoff_time)
                    continue
                raise DiscordWebhookError(f"Failed after {self.max_retries} retries: {str(e)}")

        raise DiscordWebhookError("Unexpected retry loop exit")

    def ping(self, dry_run: bool = False) -> Dict[str, Any]:
        """Send ping message to test Discord connectivity"""
        payload = {
            "content": "🏓 Beacon Discord transport ping test",
            "embeds": [{
                "title": "Transport Test",
                "description": "Discord transport is operational",
                "color": 0x00ff00,
                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
            }]
        }

        try:
            result = self._make_request(payload, dry_run)
            logger.info("Discord ping successful")
            return result
        except Exception as e:
            logger.error(f"Discord ping failed: {str(e)}")
            raise

    def send(self, message: str, embeds: Optional[List[Dict[str, Any]]] = None,
             username: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Send message to Discord channel"""
        payload = {"content": message}

        if embeds:
            payload["embeds"] = embeds

        if username:
            payload["username"] = username

        try:
            result = self._make_request(payload, dry_run)
            logger.info(f"Discord message sent successfully")
            return result
        except Exception as e:
            logger.error(f"Discord send failed: {str(e)}")
            raise

class DiscordListener:
    """Optional lightweight listener for Discord channel messages"""

    def __init__(self, bot_token: str, channel_id: str, poll_interval: int = 30):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.poll_interval = poll_interval
        self.last_message_id = None
        self._running = False

    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bot {self.bot_token}',
            'User-Agent': 'Beacon-Discord-Listener/1.0'
        }

    def _fetch_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent messages from Discord channel"""
        url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages"
        params = {'limit': limit}

        if self.last_message_id:
            params['after'] = self.last_message_id

        try:
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=15)

            if response.status_code == 429:
                retry_after = float(response.headers.get('Retry-After', 5))
                logger.warning(f"Rate limited while fetching messages, waiting {retry_after}s")
                time.sleep(retry_after)
                return []

            if response.status_code != 200:
                logger.error(f"Failed to fetch messages: HTTP {response.status_code}")
                return []

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Error fetching Discord messages: {str(e)}")
            return []

    def poll_once(self) -> List[Dict[str, Any]]:
        """Poll Discord for new messages once"""
        messages = self._fetch_messages()

        if messages:
            # Update last seen message ID
            self.last_message_id = messages[0]['id']
            # Return messages in chronological order
            messages.reverse()

        return messages

    def start_polling(self, callback=None):
        """Start polling Discord for new messages"""
        self._running = True
        logger.info(f"Starting Discord listener for channel {self.channel_id}")

        while self._running:
            try:
                messages = self.poll_once()

                for message in messages:
                    if callback:
                        callback(message)
                    else:
                        logger.info(f"New message: {message.get('content', '(no content)')}")

            except Exception as e:
                logger.error(f"Error in Discord polling loop: {str(e)}")

            time.sleep(self.poll_interval)

    def stop_polling(self):
        """Stop the polling loop"""
        self._running = False
        logger.info("Discord listener stopped")

def create_transport(webhook_url: str, **kwargs) -> DiscordTransport:
    """Factory function to create Discord transport"""
    return DiscordTransport(webhook_url, **kwargs)

def create_listener(bot_token: str, channel_id: str, **kwargs) -> DiscordListener:
    """Factory function to create Discord listener"""
    return DiscordListener(bot_token, channel_id, **kwargs)
