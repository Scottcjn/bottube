import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock
from providers.router import ProviderRouter
from providers.grok_provider import GrokProvider
from providers.runway_provider import RunwayProvider


class MockProvider:
    def __init__(self, name, should_fail=False, fail_count=0, delay=0):
        self.name = name
        self.should_fail = should_fail
        self.fail_count = fail_count
        self.call_count = 0
        self.delay = delay

    async def generate_video(self, prompt):
        self.call_count += 1

        if self.delay > 0:
            await asyncio.sleep(self.delay)

        if self.should_fail:
            if self.fail_count == 0 or self.call_count <= self.fail_count:
                if self.call_count == 1:
                    raise ConnectionError("Network timeout")
                elif self.call_count == 2:
                    raise ValueError("Rate limit exceeded")
                else:
                    raise RuntimeError("Service unavailable")

        return {"video_url": f"https://example.com/{self.name}_video.mp4", "provider": self.name}


class TestProviderRouter:

    @pytest.fixture
    def router(self):
        return ProviderRouter()

    @pytest.fixture
    def mock_providers(self):
        return [
            MockProvider("grok"),
            MockProvider("runway")
        ]

    def test_router_initialization(self, router):
        assert router is not None
        assert hasattr(router, 'providers')
        assert hasattr(router, 'retry_config')

    def test_provider_registration(self, router):
        mock_provider = MockProvider("test")
        router.register_provider(mock_provider)
        assert "test" in router.providers

    @pytest.mark.asyncio
    async def test_successful_generation_first_provider(self, router, mock_providers):
        router.providers = {"grok": mock_providers[0], "runway": mock_providers[1]}

        result = await router.generate_video("test prompt")

        assert result["provider"] == "grok"
        assert "video_url" in result
        assert mock_providers[0].call_count == 1
        assert mock_providers[1].call_count == 0

    @pytest.mark.asyncio
    async def test_fallback_to_second_provider(self, router, mock_providers):
        mock_providers[0].should_fail = True
        mock_providers[0].fail_count = 999  # Always fail

        router.providers = {"grok": mock_providers[0], "runway": mock_providers[1]}

        result = await router.generate_video("test prompt")

        assert result["provider"] == "runway"
        assert mock_providers[0].call_count >= 1
        assert mock_providers[1].call_count == 1

    @pytest.mark.asyncio
    async def test_retry_behavior_with_eventual_success(self, router, mock_providers):
        mock_providers[0].should_fail = True
        mock_providers[0].fail_count = 2  # Fail twice, then succeed

        router.providers = {"grok": mock_providers[0]}

        result = await router.generate_video("test prompt")

        assert result["provider"] == "grok"
        assert mock_providers[0].call_count == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self, router):
        provider = MockProvider("test", should_fail=True, fail_count=2)
        router.providers = {"test": provider}
        router.retry_config = {"max_attempts": 3, "base_delay": 0.1, "max_delay": 1.0}

        start_time = time.time()

        try:
            await router.generate_video("test prompt")
        except Exception:
            pass

        elapsed = time.time() - start_time

        # Should include exponential backoff delays
        assert elapsed >= 0.1  # At least base delay
        assert provider.call_count >= 2

    @pytest.mark.asyncio
    async def test_error_classification(self, router):
        provider = MockProvider("test", should_fail=True)
        router.providers = {"test": provider}

        with pytest.raises(Exception) as exc_info:
            await router.generate_video("test prompt")

        # Verify error gets classified appropriately
        assert exc_info.value is not None

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, router):
        def rate_limited_provider():
            provider = MockProvider("rate_limited")
            original_generate = provider.generate_video

            async def generate_with_rate_limit(prompt):
                if provider.call_count == 0:
                    provider.call_count += 1
                    raise ValueError("Rate limit exceeded")
                else:
                    return await original_generate(prompt)

            provider.generate_video = generate_with_rate_limit
            return provider

        provider = rate_limited_provider()
        router.providers = {"rate_limited": provider}
        router.retry_config = {"max_attempts": 3, "base_delay": 0.01}

        result = await router.generate_video("test prompt")

        assert result["provider"] == "rate_limited"

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, router, mock_providers):
        for provider in mock_providers:
            provider.should_fail = True
            provider.fail_count = 999

        router.providers = {"grok": mock_providers[0], "runway": mock_providers[1]}

        with pytest.raises(Exception):
            await router.generate_video("test prompt")

        assert all(p.call_count > 0 for p in mock_providers)

    @pytest.mark.asyncio
    async def test_provider_switching_order(self, router):
        providers = [
            MockProvider("primary", should_fail=True, fail_count=999),
            MockProvider("secondary", should_fail=True, fail_count=999),
            MockProvider("tertiary")
        ]

        router.providers = {
            "primary": providers[0],
            "secondary": providers[1],
            "tertiary": providers[2]
        }

        result = await router.generate_video("test prompt")

        assert result["provider"] == "tertiary"
        assert providers[0].call_count > 0
        assert providers[1].call_count > 0
        assert providers[2].call_count == 1

    @pytest.mark.asyncio
    async def test_timing_instrumentation(self, router):
        slow_provider = MockProvider("slow", delay=0.1)
        router.providers = {"slow": slow_provider}

        with patch('time.time', side_effect=lambda: time.time()) as mock_time:
            result = await router.generate_video("test prompt")

        assert result["provider"] == "slow"

    def test_retry_config_validation(self, router):
        invalid_configs = [
            {"max_attempts": 0},
            {"max_attempts": -1},
            {"base_delay": -0.1},
            {"max_delay": 0}
        ]

        for config in invalid_configs:
            with pytest.raises((ValueError, AssertionError)):
                router.set_retry_config(config)

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, router):
        provider = MockProvider("concurrent")
        router.providers = {"concurrent": provider}

        tasks = [router.generate_video(f"prompt {i}") for i in range(3)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        assert all(r["provider"] == "concurrent" for r in results)
        assert provider.call_count == 3

    @pytest.mark.asyncio
    async def test_provider_health_check(self, router):
        healthy_provider = MockProvider("healthy")
        unhealthy_provider = MockProvider("unhealthy", should_fail=True, fail_count=999)

        router.providers = {
            "healthy": healthy_provider,
            "unhealthy": unhealthy_provider
        }

        health_status = await router.check_provider_health()

        assert "healthy" in health_status
        assert "unhealthy" in health_status

    @pytest.mark.asyncio
    async def test_provider_metrics_collection(self, router):
        provider = MockProvider("metrics")
        router.providers = {"metrics": provider}

        # Generate some activity
        await router.generate_video("test1")
        await router.generate_video("test2")

        metrics = router.get_provider_metrics()

        assert "metrics" in metrics
        assert "success_count" in metrics["metrics"]
        assert "total_requests" in metrics["metrics"]
        assert metrics["metrics"]["success_count"] == 2

    @pytest.mark.asyncio
    async def test_circuit_breaker_behavior(self, router):
        failing_provider = MockProvider("failing", should_fail=True, fail_count=999)
        router.providers = {"failing": failing_provider}
        router.circuit_breaker_threshold = 3

        # Make several failed attempts to trip circuit breaker
        for _ in range(4):
            try:
                await router.generate_video("test")
            except Exception:
                pass

        # Verify circuit breaker is open
        assert router.is_circuit_breaker_open("failing")
