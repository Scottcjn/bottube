import json
import time
import logging
import requests
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DiscordTransportError(Exception):
    """Discord transport specific error."""
    pass


class DiscordRateLimitError(DiscordTransportError):
    """Discord rate limit error with retry info."""
    def __init__(self, message: str, retry_after: float = 1.0):
        super().__init__(message)
        self.retry_after = retry_after


class DiscordTransport:
    """Discord transport with hardened error handling and optional listener mode."""

    def __init__(self, webhook_url: str, max_retries: int = 3, listener_mode: bool = False):
        self.webhook_url = webhook_url
        self.max_retries = max_retries
        self.listener_mode = listener_mode
        self.session = requests.Session()
        self.base_delay = 1.0
        self._validate_webhook_url()

        # Extract webhook info for API calls
        self._parse_webhook_url()

    def _validate_webhook_url(self) -> None:
        """Validate Discord webhook URL format."""
        if not self.webhook_url:
            raise ValueError("Discord webhook URL is required")

        parsed = urlparse(self.webhook_url)
        if not parsed.netloc.endswith('discord.com') and not parsed.netloc.endswith('discordapp.com'):
            raise ValueError("Invalid Discord webhook URL domain")

        if '/webhooks/' not in parsed.path:
            raise ValueError("Invalid Discord webhook URL format")

    def _parse_webhook_url(self) -> None:
        """Parse webhook URL to extract ID and token."""
        try:
            parts = self.webhook_url.split('/webhooks/')[1].split('/')
            self.webhook_id = parts[0]
            self.webhook_token = parts[1] if len(parts) > 1 else None
        except (IndexError, AttributeError):
            raise ValueError("Could not parse webhook ID/token from URL")

    def _exponential_backoff(self, attempt: int, base_delay: float = None) -> float:
        """Calculate exponential backoff delay."""
        delay = (base_delay or self.base_delay) * (2 ** attempt)
        # Add jitter and cap at 60 seconds
        jitter = delay * 0.1
        return min(delay + jitter, 60.0)

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Handle Discord API response with proper error handling."""
        if response.status_code == 204:
            return {"success": True, "message": "Message sent successfully"}

        if response.status_code == 429:
            # Rate limited
            retry_after = float(response.headers.get('Retry-After', 1.0))
            raise DiscordRateLimitError(
                f"Rate limited by Discord API",
                retry_after=retry_after
            )

        if 400 <= response.status_code < 500:
            # Client error
            try:
                error_data = response.json()
                error_msg = error_data.get('message', f"HTTP {response.status_code}")
            except (ValueError, json.JSONDecodeError):
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            raise DiscordTransportError(f"Discord API client error: {error_msg}")

        if response.status_code >= 500:
            # Server error
            raise DiscordTransportError(f"Discord API server error: HTTP {response.status_code}")

        try:
            return response.json()
        except (ValueError, json.JSONDecodeError):
            return {"success": True, "raw_response": response.text}

    def _execute_with_retry(self, func, *args, **kwargs) -> Dict[str, Any]:
        """Execute function with exponential backoff retry logic."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except DiscordRateLimitError as e:
                last_exception = e
                if attempt >= self.max_retries:
                    break

                retry_delay = max(e.retry_after, self._exponential_backoff(attempt))
                logger.warning(f"Rate limited, retrying in {retry_delay:.1f}s (attempt {attempt + 1})")
                time.sleep(retry_delay)

            except DiscordTransportError as e:
                last_exception = e
                if attempt >= self.max_retries:
                    break

                # Only retry on server errors, not client errors
                if "server error" not in str(e).lower():
                    raise

                delay = self._exponential_backoff(attempt)
                logger.warning(f"Server error, retrying in {delay:.1f}s (attempt {attempt + 1})")
                time.sleep(delay)

            except Exception as e:
                last_exception = e
                if attempt >= self.max_retries:
                    break

                delay = self._exponential_backoff(attempt)
                logger.warning(f"Unexpected error, retrying in {delay:.1f}s: {e}")
                time.sleep(delay)

        # All retries exhausted
        if last_exception:
            raise last_exception
        raise DiscordTransportError("Maximum retries exhausted")

    def ping(self) -> Dict[str, Any]:
        """Ping Discord webhook to verify connectivity."""
        def _ping():
            # Get webhook info without sending a message
            if self.webhook_token:
                url = f"https://discord.com/api/webhooks/{self.webhook_id}/{self.webhook_token}"
            else:
                url = f"https://discord.com/api/webhooks/{self.webhook_id}"

            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                webhook_info = response.json()
                return {
                    "success": True,
                    "webhook_name": webhook_info.get("name", "Unknown"),
                    "guild_id": webhook_info.get("guild_id"),
                    "channel_id": webhook_info.get("channel_id")
                }
            else:
                return self._handle_response(response)

        return self._execute_with_retry(_ping)

    def send(self, message: Union[str, Dict[str, Any]], dry_run: bool = False) -> Dict[str, Any]:
        """Send message to Discord webhook."""
        def _send():
            # Prepare payload
            if isinstance(message, str):
                payload = {"content": message}
            else:
                payload = message.copy()

            # Validate payload
            if not payload.get("content") and not payload.get("embeds"):
                raise ValueError("Message must have content or embeds")

            if dry_run:
                return {
                    "success": True,
                    "dry_run": True,
                    "payload_size": len(json.dumps(payload)),
                    "payload": payload
                }

            # Send to Discord
            params = {"wait": "true"}
            response = self.session.post(
                self.webhook_url,
                json=payload,
                params=params,
                timeout=30
            )

            return self._handle_response(response)

        return self._execute_with_retry(_send)

    def listen(self, poll_interval: int = 30, max_events: int = 50) -> List[Dict[str, Any]]:
        """Listen for Discord events (basic polling implementation)."""
        if not self.listener_mode:
            raise DiscordTransportError("Listener mode not enabled")

        def _poll_events():
            # This would require Discord bot token and more complex setup
            # For now, return webhook execution logs if available
            if self.webhook_token:
                url = f"https://discord.com/api/webhooks/{self.webhook_id}/{self.webhook_token}"
                response = self.session.get(url, timeout=10)

                if response.status_code == 200:
                    webhook_data = response.json()
                    return [{
                        "type": "webhook_status",
                        "timestamp": time.time(),
                        "webhook_id": self.webhook_id,
                        "name": webhook_data.get("name"),
                        "guild_id": webhook_data.get("guild_id"),
                        "channel_id": webhook_data.get("channel_id")
                    }]
                else:
                    self._handle_response(response)

            return []

        try:
            return self._execute_with_retry(_poll_events)
        except Exception as e:
            logger.error(f"Error polling Discord events: {e}")
            return []

    def get_webhook_info(self) -> Dict[str, Any]:
        """Get detailed webhook information."""
        def _get_info():
            if not self.webhook_token:
                raise DiscordTransportError("Webhook token required for detailed info")

            url = f"https://discord.com/api/webhooks/{self.webhook_id}/{self.webhook_token}"
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                return self._handle_response(response)

        return self._execute_with_retry(_get_info)

    def modify_webhook(self, name: str = None, avatar: str = None) -> Dict[str, Any]:
        """Modify webhook properties."""
        def _modify():
            if not self.webhook_token:
                raise DiscordTransportError("Webhook token required for modification")

            payload = {}
            if name:
                payload["name"] = name
            if avatar:
                payload["avatar"] = avatar

            if not payload:
                raise ValueError("No modifications specified")

            url = f"https://discord.com/api/webhooks/{self.webhook_id}/{self.webhook_token}"
            response = self.session.patch(url, json=payload, timeout=10)

            return self._handle_response(response)

        return self._execute_with_retry(_modify)

    def close(self) -> None:
        """Close transport session."""
        if hasattr(self, 'session'):
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Factory function for easy instantiation
def create_discord_transport(webhook_url: str, **kwargs) -> DiscordTransport:
    """Create Discord transport instance with sensible defaults."""
    return DiscordTransport(webhook_url, **kwargs)
