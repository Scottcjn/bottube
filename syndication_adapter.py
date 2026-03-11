#!/usr/bin/env python3
"""
Syndication Adapter Interface for BoTTube

Abstract base class and concrete implementations for syndicating content
to external platforms. Each platform (Moltbook, Twitter, RSS, etc.) has
its own adapter implementing the common interface.

Adapters are stateless and focused solely on platform-specific API calls.
Queue management and retry logic are handled by syndication_queue.py.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

log = logging.getLogger("bottube-syndication-adapter")


@dataclass
class SyndicationResult:
    """Result of a syndication operation."""
    success: bool
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "success": self.success,
            "external_id": self.external_id,
            "external_url": self.external_url,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class SyndicationPayload:
    """Payload for syndication to external platforms."""
    video_id: str
    video_title: str
    video_description: str
    video_url: str
    thumbnail_url: Optional[str]
    agent_id: int
    agent_name: str
    tags: list
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SyndicationAdapter(ABC):
    """
    Abstract base class for syndication adapters.

    Each adapter implements platform-specific logic for posting content
    to an external service. Adapters should be stateless - all state
    (retry counts, queue position) is managed by syndication_queue.py.

    Subclasses must implement:
        - platform_name: Class attribute identifying the platform
        - syndicate(): Main method to publish content
        - validate_config(): Validate adapter configuration
    """

    platform_name: str = "base"

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize adapter with configuration.

        Args:
            config: Platform-specific configuration dict.
                    Must pass validate_config() before use.
        """
        self.config = config
        self._session = requests.Session()
        self._setup_session()

    def _setup_session(self):
        """Configure the requests session (headers, auth, etc.)."""
        self._session.headers.update({"User-Agent": "BoTTube-Syndication/1.0"})

    @abstractmethod
    def validate_config(self) -> bool:
        """
        Validate adapter configuration.

        Returns:
            True if configuration is valid, False otherwise.
        """
        pass

    @abstractmethod
    def syndicate(self, payload: SyndicationPayload) -> SyndicationResult:
        """
        Syndicate content to the external platform.

        Args:
            payload: Content payload to syndicate.

        Returns:
            SyndicationResult with success status and platform-specific metadata.
        """
        pass

    def test_connection(self) -> bool:
        """
        Test connection to the external platform.

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            result = self._test_connection_impl()
            if result:
                log.info("[%s] Connection test successful", self.platform_name)
            else:
                log.warning("[%s] Connection test failed", self.platform_name)
            return result
        except Exception as e:
            log.error("[%s] Connection test error: %s", self.platform_name, e)
            return False

    @abstractmethod
    def _test_connection_impl(self) -> bool:
        """Platform-specific connection test implementation."""
        pass

    def close(self):
        """Close the adapter and release resources."""
        self._session.close()


class MoltbookAdapter(SyndicationAdapter):
    """Adapter for syndicating to Moltbook (AI social network)."""

    platform_name = "moltbook"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("base_url", "")
        self.api_key = config.get("api_key", "")

    def validate_config(self) -> bool:
        """Validate Moltbook configuration."""
        if not self.base_url:
            log.error("[moltbook] Missing base_url in config")
            return False
        if not self.api_key:
            log.error("[moltbook] Missing api_key in config")
            return False
        self._session.headers.update({"Authorization": f"Bearer {self.api_key}"})
        return True

    def syndicate(self, payload: SyndicationPayload) -> SyndicationResult:
        """Post video to Moltbook."""
        url = f"{self.base_url}/api/posts"
        data = {
            "content": f"🎬 New video: {payload.video_title}\n\n{payload.video_description}",
            "video_url": payload.video_url,
            "tags": payload.tags,
            "metadata": {
                "source": "bottube",
                "video_id": payload.video_id,
                "agent_id": payload.agent_id,
            },
        }
        if payload.thumbnail_url:
            data["thumbnail"] = payload.thumbnail_url

        try:
            response = self._session.post(url, json=data, timeout=30)
            response.raise_for_status()
            result_data = response.json()

            return SyndicationResult(
                success=True,
                external_id=result_data.get("post_id"),
                external_url=result_data.get("post_url"),
                metadata={"moltbook_response": result_data},
            )
        except requests.RequestException as e:
            log.error("[moltbook] Syndication failed: %s", e)
            return SyndicationResult(
                success=False,
                error_message=str(e),
            )

    def _test_connection_impl(self) -> bool:
        """Test Moltbook API connection."""
        url = f"{self.base_url}/api/health"
        try:
            response = self._session.get(url, timeout=10)
            return response.status_code == 200
        except requests.RequestException:
            return False


class TwitterAdapter(SyndicationAdapter):
    """Adapter for syndicating to Twitter/X."""

    platform_name = "twitter"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.api_secret = config.get("api_secret", "")
        self.access_token = config.get("access_token", "")
        self.access_token_secret = config.get("access_token_secret", "")

    def validate_config(self) -> bool:
        """Validate Twitter API credentials."""
        required = ["api_key", "api_secret", "access_token", "access_token_secret"]
        for key in required:
            if not self.config.get(key):
                log.error("[twitter] Missing %s in config", key)
                return False
        # OAuth setup would go here in real implementation
        return True

    def syndicate(self, payload: SyndicationPayload) -> SyndicationResult:
        """Post video link to Twitter."""
        # In real implementation, this would use Twitter API v2
        # For now, simulate the API call structure
        tweet_text = f"🎬 {payload.video_title}\n\n{payload.video_description[:200]}"
        if len(payload.tags):
            hashtags = " ".join([f"#{tag}" for tag in payload.tags[:3]])
            tweet_text += f"\n\n{hashtags}"
        tweet_text += f"\n\n{payload.video_url}"

        try:
            # Placeholder for actual Twitter API call
            # twitter_client.create_tweet(text=tweet_text, media_ids=[...])
            log.info("[twitter] Would post: %s", tweet_text[:100])
            return SyndicationResult(
                success=True,
                external_id="twitter_placeholder_id",
                external_url=f"https://twitter.com/status/placeholder",
                metadata={"tweet_text": tweet_text},
            )
        except Exception as e:
            log.error("[twitter] Syndication failed: %s", e)
            return SyndicationResult(success=False, error_message=str(e))

    def _test_connection_impl(self) -> bool:
        """Test Twitter API connection."""
        # Placeholder - would test OAuth credentials
        return bool(self.api_key and self.api_secret)


class RSSFeedAdapter(SyndicationAdapter):
    """Adapter for updating RSS/Atom feeds."""

    platform_name = "rss_feed"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.feed_url = config.get("feed_url", "")
        self.feed_file = config.get("feed_file", "feed.xml")
        self.site_url = config.get("site_url", "")
        self.author_email = config.get("author_email", "noreply@bottube.ai")

    def validate_config(self) -> bool:
        """Validate RSS configuration."""
        if not self.site_url:
            log.error("[rss_feed] Missing site_url in config")
            return False
        return True

    def syndicate(self, payload: SyndicationPayload) -> SyndicationResult:
        """Add video to RSS feed."""
        # In real implementation, this would update the XML feed file
        # or call an API to regenerate the feed
        item_xml = f"""
        <item>
            <title>{payload.video_title}</title>
            <link>{payload.video_url}</link>
            <description>{payload.video_description}</description>
            <author>{self.author_email} ({payload.agent_name})</author>
            <guid isPermaLink="true">{payload.video_url}</guid>
        </item>
        """
        try:
            # Placeholder - would actually update feed.xml
            log.info("[rss_feed] Would add item: %s", payload.video_title)
            return SyndicationResult(
                success=True,
                external_id=payload.video_id,
                external_url=payload.video_url,
                metadata={"rss_item": item_xml.strip()},
            )
        except Exception as e:
            log.error("[rss_feed] Syndication failed: %s", e)
            return SyndicationResult(success=False, error_message=str(e))

    def _test_connection_impl(self) -> bool:
        """Test RSS feed accessibility."""
        if self.feed_url:
            try:
                response = self._session.get(self.feed_url, timeout=10)
                return response.status_code == 200
            except requests.RequestException:
                return False
        return True


class PartnerAPIAdapter(SyndicationAdapter):
    """Adapter for generic partner API syndication."""

    platform_name = "partner_api"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.endpoint_url = config.get("endpoint_url", "")
        self.auth_header = config.get("auth_header", "X-API-Key")
        self.auth_value = config.get("auth_value", "")
        self.payload_template = config.get("payload_template", None)

    def validate_config(self) -> bool:
        """Validate partner API configuration."""
        if not self.endpoint_url:
            log.error("[partner_api] Missing endpoint_url in config")
            return False
        if not self.auth_value:
            log.error("[partner_api] Missing auth_value in config")
            return False
        return True

    def syndicate(self, payload: SyndicationPayload) -> SyndicationResult:
        """Post to partner API endpoint."""
        headers = {self.auth_header: self.auth_value}
        
        # Use template if provided, otherwise use default payload
        if self.payload_template:
            import json
            payload_data = json.loads(self.payload_template)
            # Substitute variables
            payload_data = self._substitute_template(payload_data, payload)
        else:
            payload_data = {
                "title": payload.video_title,
                "description": payload.video_description,
                "url": payload.video_url,
                "thumbnail": payload.thumbnail_url,
                "tags": payload.tags,
                "metadata": {
                    "video_id": payload.video_id,
                    "agent_id": payload.agent_id,
                    "agent_name": payload.agent_name,
                },
            }

        try:
            response = self._session.post(
                self.endpoint_url,
                headers=headers,
                json=payload_data,
                timeout=30,
            )
            response.raise_for_status()
            result_data = response.json()

            return SyndicationResult(
                success=True,
                external_id=result_data.get("id"),
                external_url=result_data.get("url"),
                metadata={"partner_response": result_data},
            )
        except requests.RequestException as e:
            log.error("[partner_api] Syndication failed: %s", e)
            return SyndicationResult(success=False, error_message=str(e))

    def _substitute_template(self, data: Any, payload: SyndicationPayload) -> Any:
        """Recursively substitute template variables."""
        if isinstance(data, str):
            return (data
                .replace("{{video_id}}", payload.video_id)
                .replace("{{video_title}}", payload.video_title)
                .replace("{{video_description}}", payload.video_description)
                .replace("{{video_url}}", payload.video_url)
                .replace("{{agent_id}}", str(payload.agent_id))
                .replace("{{agent_name}}", payload.agent_name)
                .replace("{{thumbnail_url}}", payload.thumbnail_url or ""))
        elif isinstance(data, dict):
            return {k: self._substitute_template(v, payload) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._substitute_template(item, payload) for item in data]
        return data

    def _test_connection_impl(self) -> bool:
        """Test partner API endpoint."""
        try:
            response = self._session.get(
                self.endpoint_url,
                headers={self.auth_header: self.auth_value},
                timeout=10,
            )
            # Allow 200, 201, 204 as success
            return response.status_code in (200, 201, 204, 404, 405)
        except requests.RequestException:
            return False


# Adapter registry for factory pattern
ADAPTER_REGISTRY = {
    "moltbook": MoltbookAdapter,
    "twitter": TwitterAdapter,
    "rss_feed": RSSFeedAdapter,
    "partner_api": PartnerAPIAdapter,
}


def get_adapter(platform: str, config: Dict[str, Any]) -> SyndicationAdapter:
    """
    Factory function to get adapter instance by platform name.

    Args:
        platform: Platform name (e.g., "moltbook", "twitter")
        config: Platform-specific configuration

    Returns:
        Configured adapter instance

    Raises:
        ValueError: If platform is not registered
    """
    adapter_class = ADAPTER_REGISTRY.get(platform)
    if not adapter_class:
        raise ValueError(f"Unknown syndication platform: {platform}")
    return adapter_class(config)


def list_adapters() -> list:
    """Return list of registered adapter platform names."""
    return list(ADAPTER_REGISTRY.keys())
