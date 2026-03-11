#!/usr/bin/env python3
"""
Tests for Syndication Adapter (Issue #310)

Tests cover:
- Adapter base class and interface
- Concrete adapters (Moltbook, Twitter, RSS, Partner API)
- Adapter factory and registry
- Payload and result data classes
"""

import pytest
import requests
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syndication_adapter import (
    SyndicationAdapter,
    SyndicationResult,
    SyndicationPayload,
    MoltbookAdapter,
    TwitterAdapter,
    RSSFeedAdapter,
    PartnerAPIAdapter,
    get_adapter,
    list_adapters,
    ADAPTER_REGISTRY,
)


class TestSyndicationResult:
    """Tests for SyndicationResult dataclass."""

    def test_success_result(self):
        """Test successful result creation."""
        result = SyndicationResult(
            success=True,
            external_id="ext_123",
            external_url="https://example.com/post/123",
        )
        assert result.success is True
        assert result.external_id == "ext_123"
        assert result.external_url == "https://example.com/post/123"
        assert result.error_message is None
        assert result.metadata == {}

    def test_failure_result(self):
        """Test failed result creation."""
        result = SyndicationResult(
            success=False,
            error_message="Connection timeout",
        )
        assert result.success is False
        assert result.error_message == "Connection timeout"
        assert result.external_id is None

    def test_to_dict(self):
        """Test result serialization."""
        result = SyndicationResult(
            success=True,
            external_id="123",
            metadata={"key": "value"},
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["external_id"] == "123"
        assert d["metadata"] == {"key": "value"}


class TestSyndicationPayload:
    """Tests for SyndicationPayload dataclass."""

    def test_payload_creation(self):
        """Test payload creation with required fields."""
        payload = SyndicationPayload(
            video_id="vid_123",
            video_title="Test Video",
            video_description="A test video",
            video_url="https://bottube.ai/videos/vid_123",
            thumbnail_url="https://bottube.ai/thumbs/vid_123.jpg",
            agent_id=42,
            agent_name="test_agent",
            tags=["ai", "test"],
        )
        assert payload.video_id == "vid_123"
        assert payload.tags == ["ai", "test"]
        assert payload.metadata == {}

    def test_payload_with_metadata(self):
        """Test payload with custom metadata."""
        payload = SyndicationPayload(
            video_id="vid_123",
            video_title="Test",
            video_description="Desc",
            video_url="https://example.com",
            thumbnail_url=None,
            agent_id=1,
            agent_name="agent",
            tags=[],
            metadata={"custom": "data"},
        )
        assert payload.metadata == {"custom": "data"}


class TestAdapterInterface:
    """Tests for abstract adapter interface."""

    def test_abstract_methods(self):
        """Test that abstract methods must be implemented."""
        with pytest.raises(TypeError):
            SyndicationAdapter({})

    def test_concrete_adapter_instantiation(self):
        """Test that concrete adapters can be instantiated."""
        adapter = MoltbookAdapter({"base_url": "https://moltbook.com", "api_key": "key"})
        assert adapter.platform_name == "moltbook"


class TestMoltbookAdapter:
    """Tests for Moltbook adapter."""

    def test_validate_config_missing_url(self):
        """Test validation fails without base_url."""
        adapter = MoltbookAdapter({"api_key": "key"})
        assert adapter.validate_config() is False

    def test_validate_config_missing_key(self):
        """Test validation fails without api_key."""
        adapter = MoltbookAdapter({"base_url": "https://moltbook.com"})
        assert adapter.validate_config() is False

    def test_validate_config_success(self):
        """Test validation succeeds with required config."""
        adapter = MoltbookAdapter({
            "base_url": "https://moltbook.com",
            "api_key": "test_key",
        })
        assert adapter.validate_config() is True

    @patch('syndication_adapter.requests.Session')
    def test_syndicate_success(self, mock_session_class):
        """Test successful syndication to Moltbook."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "post_id": "post_123",
            "post_url": "https://moltbook.com/posts/post_123",
        }
        mock_session.post.return_value = mock_response

        adapter = MoltbookAdapter({
            "base_url": "https://moltbook.com",
            "api_key": "test_key",
        })
        adapter.validate_config()

        payload = SyndicationPayload(
            video_id="vid_123",
            video_title="Test Video",
            video_description="Test description",
            video_url="https://bottube.ai/videos/vid_123",
            thumbnail_url="https://bottube.ai/thumbs/vid_123.jpg",
            agent_id=42,
            agent_name="test_agent",
            tags=["ai", "test"],
        )

        result = adapter.syndicate(payload)

        assert result.success is True
        assert result.external_id == "post_123"
        mock_session.post.assert_called_once()

    @patch('syndication_adapter.requests.Session')
    def test_syndicate_failure(self, mock_session_class):
        """Test failed syndication."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_session.post.side_effect = requests.RequestException("Connection error")

        adapter = MoltbookAdapter({
            "base_url": "https://moltbook.com",
            "api_key": "test_key",
        })
        adapter.validate_config()

        payload = SyndicationPayload(
            video_id="vid_123",
            video_title="Test",
            video_description="Desc",
            video_url="https://example.com",
            thumbnail_url=None,
            agent_id=1,
            agent_name="agent",
            tags=[],
        )

        result = adapter.syndicate(payload)

        assert result.success is False
        assert "Connection error" in result.error_message


class TestTwitterAdapter:
    """Tests for Twitter adapter."""

    def test_validate_config_missing_fields(self):
        """Test validation fails without required fields."""
        adapter = TwitterAdapter({})
        assert adapter.validate_config() is False

    def test_validate_config_success(self):
        """Test validation with all required fields."""
        adapter = TwitterAdapter({
            "api_key": "key",
            "api_secret": "secret",
            "access_token": "token",
            "access_token_secret": "token_secret",
        })
        assert adapter.validate_config() is True

    def test_syndicate_placeholder(self):
        """Test Twitter syndication (placeholder implementation)."""
        adapter = TwitterAdapter({
            "api_key": "key",
            "api_secret": "secret",
            "access_token": "token",
            "access_token_secret": "token_secret",
        })

        payload = SyndicationPayload(
            video_id="vid_123",
            video_title="Test Video",
            video_description="Test description",
            video_url="https://bottube.ai/videos/vid_123",
            thumbnail_url=None,
            agent_id=1,
            agent_name="agent",
            tags=["ai"],
        )

        result = adapter.syndicate(payload)

        # Placeholder always succeeds
        assert result.success is True
        assert "tweet_text" in result.metadata


class TestRSSFeedAdapter:
    """Tests for RSS feed adapter."""

    def test_validate_config(self):
        """Test RSS adapter validation."""
        adapter = RSSFeedAdapter({"site_url": "https://bottube.ai"})
        assert adapter.validate_config() is True

    def test_validate_config_missing_site_url(self):
        """Test validation fails without site_url."""
        adapter = RSSFeedAdapter({})
        assert adapter.validate_config() is False

    def test_syndicate(self):
        """Test RSS feed syndication."""
        adapter = RSSFeedAdapter({"site_url": "https://bottube.ai"})

        payload = SyndicationPayload(
            video_id="vid_123",
            video_title="Test Video",
            video_description="Description",
            video_url="https://bottube.ai/videos/vid_123",
            thumbnail_url=None,
            agent_id=1,
            agent_name="agent",
            tags=[],
        )

        result = adapter.syndicate(payload)

        assert result.success is True
        assert "rss_item" in result.metadata
        assert "Test Video" in result.metadata["rss_item"]


class TestPartnerAPIAdapter:
    """Tests for Partner API adapter."""

    def test_validate_config(self):
        """Test Partner API adapter validation."""
        adapter = PartnerAPIAdapter({
            "endpoint_url": "https://api.partner.com/syndicate",
            "auth_value": "secret_key",
        })
        assert adapter.validate_config() is True

    def test_validate_config_missing_endpoint(self):
        """Test validation fails without endpoint_url."""
        adapter = PartnerAPIAdapter({"auth_value": "key"})
        assert adapter.validate_config() is False

    def test_validate_config_missing_auth(self):
        """Test validation fails without auth_value."""
        adapter = PartnerAPIAdapter({"endpoint_url": "https://api.com"})
        assert adapter.validate_config() is False

    @patch('syndication_adapter.requests.Session')
    def test_syndicate_with_template(self, mock_session_class):
        """Test syndication with payload template."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "partner_123", "url": "https://partner.com/123"}
        mock_session.post.return_value = mock_response

        adapter = PartnerAPIAdapter({
            "endpoint_url": "https://api.partner.com/syndicate",
            "auth_header": "X-API-Key",
            "auth_value": "secret",
            "payload_template": '{"title": "{{video_title}}", "url": "{{video_url}}"}',
        })

        payload = SyndicationPayload(
            video_id="vid_123",
            video_title="My Video",
            video_description="Desc",
            video_url="https://bottube.ai/videos/vid_123",
            thumbnail_url=None,
            agent_id=1,
            agent_name="agent",
            tags=[],
        )

        result = adapter.syndicate(payload)

        assert result.success is True
        assert result.external_id == "partner_123"

    def test_template_substitution(self):
        """Test template variable substitution."""
        adapter = PartnerAPIAdapter({
            "endpoint_url": "https://api.com",
            "auth_value": "key",
        })

        payload = SyndicationPayload(
            video_id="vid_123",
            video_title="Test Title",
            video_description="Test Desc",
            video_url="https://example.com/vid_123",
            thumbnail_url="https://example.com/thumb.jpg",
            agent_id=42,
            agent_name="test_agent",
            tags=[],
        )

        template = {
            "title": "{{video_title}}",
            "url": "{{video_url}}",
            "agent": "{{agent_name}}",
        }

        result = adapter._substitute_template(template, payload)

        assert result["title"] == "Test Title"
        assert result["url"] == "https://example.com/vid_123"
        assert result["agent"] == "test_agent"


class TestAdapterFactory:
    """Tests for adapter factory functions."""

    def test_get_adapter_moltbook(self):
        """Test getting Moltbook adapter from factory."""
        adapter = get_adapter("moltbook", {
            "base_url": "https://moltbook.com",
            "api_key": "key",
        })
        assert isinstance(adapter, MoltbookAdapter)

    def test_get_adapter_twitter(self):
        """Test getting Twitter adapter from factory."""
        adapter = get_adapter("twitter", {
            "api_key": "key",
            "api_secret": "secret",
            "access_token": "token",
            "access_token_secret": "secret",
        })
        assert isinstance(adapter, TwitterAdapter)

    def test_get_adapter_rss(self):
        """Test getting RSS adapter from factory."""
        adapter = get_adapter("rss_feed", {"site_url": "https://example.com"})
        assert isinstance(adapter, RSSFeedAdapter)

    def test_get_adapter_partner(self):
        """Test getting Partner API adapter from factory."""
        adapter = get_adapter("partner_api", {
            "endpoint_url": "https://api.com",
            "auth_value": "key",
        })
        assert isinstance(adapter, PartnerAPIAdapter)

    def test_get_adapter_unknown(self):
        """Test getting unknown adapter raises error."""
        with pytest.raises(ValueError, match="Unknown syndication platform"):
            get_adapter("unknown_platform", {})

    def test_list_adapters(self):
        """Test listing registered adapters."""
        adapters = list_adapters()
        assert "moltbook" in adapters
        assert "twitter" in adapters
        assert "rss_feed" in adapters
        assert "partner_api" in adapters

    def test_adapter_registry(self):
        """Test adapter registry contains expected platforms."""
        assert len(ADAPTER_REGISTRY) >= 4
        assert "moltbook" in ADAPTER_REGISTRY
        assert ADAPTER_REGISTRY["moltbook"] == MoltbookAdapter


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
