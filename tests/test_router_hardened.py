"""Tests for hardened provider router."""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

from providers.router_hardened import (
    ErrorCategory,
    ProviderError,
    ProviderMetrics,
    RouterMetrics,
    categorize_error,
    with_retry,
    choose_provider,
    get_provider_status,
)


class TestErrorCategorization:
    """Test error categorization logic."""

    def test_auth_error(self):
        """Authentication errors should be categorized as AUTH."""
        error = Exception("Invalid API key")
        result = categorize_error(error, "grok")
        assert result.category == ErrorCategory.AUTH
        assert "grok" in str(result)

    def test_throttled_error(self):
        """Rate limit errors should be categorized as THROTTLED."""
        error = Exception("Rate limit exceeded (429)")
        result = categorize_error(error, "runway")
        assert result.category == ErrorCategory.THROTTLED

    def test_transient_error(self):
        """Network errors should be categorized as TRANSIENT."""
        error = TimeoutError("Connection timeout")
        result = categorize_error(error, "grok")
        assert result.category == ErrorCategory.TRANSIENT

    def test_permanent_error(self):
        """Invalid input errors should be categorized as PERMANENT."""
        error = Exception("Invalid prompt: too long")
        result = categorize_error(error, "runway")
        assert result.category == ErrorCategory.PERMANENT

    def test_unknown_error(self):
        """Uncategorized errors should be UNKNOWN."""
        error = Exception("Something weird happened")
        result = categorize_error(error, "grok")
        assert result.category == ErrorCategory.UNKNOWN


class TestProviderMetrics:
    """Test metrics collection."""

    def test_metrics_duration(self):
        """Duration should be calculated correctly."""
        metrics = ProviderMetrics(provider="grok")
        time.sleep(0.01)  # Small delay
        metrics.end_time = time.time()
        
        assert metrics.duration_ms >= 10  # At least 10ms
        assert metrics.duration_ms < 1000  # Less than 1 second

    def test_metrics_to_dict(self):
        """Metrics should serialize to dict."""
        metrics = ProviderMetrics(
            provider="grok",
            success=True,
            error_category=ErrorCategory.TRANSIENT,
            retry_count=2,
        )
        metrics.end_time = time.time()
        
        d = metrics.to_dict()
        assert d["provider"] == "grok"
        assert d["success"] is True
        assert d["error_category"] == "transient"
        assert d["retry_count"] == 2


class TestRouterMetrics:
    """Test router-level metrics."""

    def test_router_metrics_aggregation(self):
        """Router should aggregate provider metrics."""
        router = RouterMetrics(prompt="test", primary_provider="grok")
        
        # Add some provider metrics
        m1 = ProviderMetrics(provider="grok", success=False)
        m1.end_time = time.time()
        m2 = ProviderMetrics(provider="runway", success=True)
        m2.end_time = time.time()
        
        router.provider_metrics = [m1, m2]
        router.total_attempts = 2
        router.fallback_used = True
        
        d = router.to_dict()
        assert d["primary_provider"] == "grok"
        assert d["fallback_used"] is True
        assert d["total_attempts"] == 2
        assert len(d["providers"]) == 2


class TestRetryDecorator:
    """Test retry logic."""

    def test_success_no_retry(self):
        """Successful calls should not retry."""
        call_count = 0
        
        @with_retry(max_retries=2)
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = success_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_on_transient_error(self):
        """Transient errors should trigger retry."""
        call_count = 0
        
        @with_retry(max_retries=2, base_delay=0.01)
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ProviderError("timeout", ErrorCategory.TRANSIENT, "grok")
            return "success"
        
        result = fail_then_succeed()
        assert result == "success"
        assert call_count == 2

    def test_no_retry_on_permanent_error(self):
        """Permanent errors should not retry."""
        call_count = 0
        
        @with_retry(max_retries=2)
        def permanent_fail():
            nonlocal call_count
            call_count += 1
            raise ProviderError("invalid", ErrorCategory.PERMANENT, "grok")
        
        with pytest.raises(ProviderError) as exc_info:
            permanent_fail()
        
        assert call_count == 1  # No retry
        assert exc_info.value.category == ErrorCategory.PERMANENT

    def test_max_retries_exceeded(self):
        """Should fail after max retries."""
        call_count = 0
        
        @with_retry(max_retries=2, base_delay=0.01)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ProviderError("timeout", ErrorCategory.TRANSIENT, "grok")
        
        with pytest.raises(ProviderError):
            always_fail()
        
        assert call_count == 3  # Initial + 2 retries


class TestProviderSelection:
    """Test provider selection logic."""

    def test_explicit_provider(self):
        """Explicit provider preference should be respected."""
        assert choose_provider("test", prefer="grok") == "grok"
        assert choose_provider("test", prefer="runway") == "runway"

    def test_auto_detect_grok(self):
        """Should detect grok in prompt."""
        assert choose_provider("Create a grok style video") == "grok"

    def test_auto_detect_runway(self):
        """Should detect runway hints in prompt."""
        assert choose_provider("Cinematic film quality") == "runway"
        assert choose_provider("Photorealistic physics simulation") == "runway"

    def test_default_to_grok(self):
        """Should default to grok when no hints."""
        assert choose_provider("Just a simple video") == "grok"


class TestProviderStatus:
    """Test provider status checking."""

    def test_get_status(self):
        """Should return status for all providers."""
        status = get_provider_status()
        
        # Should have entries for grok and runway
        assert "grok" in status
        assert "runway" in status
        
        # Each should have availability info
        for name, info in status.items():
            assert "available" in info
            assert "name" in info


class TestIntegration:
    """Integration tests for the full router flow."""

    @patch("providers.router_hardened._PROVIDER_FACTORIES")
    def test_successful_generation(self, mock_factories):
        """Test successful video generation."""
        mock_provider = MagicMock()
        mock_result = MagicMock()
        mock_result.metadata = {}
        mock_provider.return_value.generate.return_value = mock_result
        
        mock_factories.__getitem__ = lambda self, k: mock_provider
        
        from providers.router_hardened import generate_video
        
        result = generate_video("test prompt", fallback=False, log_metrics=False)
        
        assert result is mock_result
        assert result.metadata["router_primary"] == "grok"

    @patch("providers.router_hardened._PROVIDER_FACTORIES")
    def test_fallback_on_failure(self, mock_factories):
        """Test fallback to secondary provider."""
        mock_grok = MagicMock()
        mock_grok.return_value.generate.side_effect = Exception("timeout")
        
        mock_runway = MagicMock()
        mock_result = MagicMock()
        mock_result.metadata = {}
        mock_runway.return_value.generate.return_value = mock_result
        
        mock_factories.__getitem__ = lambda self, k: mock_runway if k == "runway" else mock_grok
        
        from providers.router_hardened import generate_video
        
        result = generate_video("test prompt", fallback=True, log_metrics=False)
        
        assert result is mock_result
        assert result.metadata["router_fallback_used"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
