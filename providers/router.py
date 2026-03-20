# SPDX-License-Identifier: MIT

import asyncio
import logging
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from .grok import GrokProvider
from .runway import RunwayProvider


class ErrorCategory(Enum):
    """Error classification for provider failures"""
    AUTH = "authentication"
    THROTTLED = "rate_limited"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


@dataclass
class ProviderMetrics:
    """Track provider performance metrics"""
    success_count: int = 0
    failure_count: int = 0
    total_time: float = 0.0
    last_success: Optional[float] = None
    last_failure: Optional[float] = None
    consecutive_failures: int = 0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    @property
    def avg_response_time(self) -> float:
        total_requests = self.success_count + self.failure_count
        return self.total_time / total_requests if total_requests > 0 else 0.0


@dataclass
class RetryConfig:
    """Retry configuration with exponential backoff"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    jitter: bool = True


class ProviderError(Exception):
    """Base provider error with categorization"""

    def __init__(self, message: str, category: ErrorCategory, provider: str, original_error: Exception = None):
        super().__init__(message)
        self.category = category
        self.provider = provider
        self.original_error = original_error


class ProviderRouter:
    """Production-ready provider router with retry/fallback strategies"""

    def __init__(self, retry_config: Optional[RetryConfig] = None):
        self.logger = logging.getLogger(__name__)
        self.retry_config = retry_config or RetryConfig()

        # Initialize providers
        self.providers = {
            'grok': GrokProvider(),
            'runway': RunwayProvider()
        }

        # Provider metrics tracking
        self.metrics: Dict[str, ProviderMetrics] = {
            name: ProviderMetrics() for name in self.providers.keys()
        }

        # Provider order for deterministic fallback
        self.provider_order = ['grok', 'runway']

    def _classify_error(self, error: Exception, provider_name: str) -> ErrorCategory:
        """Classify error into categories for retry logic"""
        error_msg = str(error).lower()

        # Authentication errors
        if any(keyword in error_msg for keyword in ['unauthorized', 'invalid api key', 'authentication', '401']):
            return ErrorCategory.AUTH

        # Rate limiting
        if any(keyword in error_msg for keyword in ['rate limit', 'quota', 'throttle', '429', 'too many']):
            return ErrorCategory.THROTTLED

        # Transient errors
        if any(keyword in error_msg for keyword in ['timeout', 'connection', 'network', '500', '502', '503', '504']):
            return ErrorCategory.TRANSIENT

        # Default to permanent for unknown errors
        return ErrorCategory.PERMANENT

    def _should_retry(self, error_category: ErrorCategory) -> bool:
        """Determine if error category should trigger retry"""
        return error_category in [ErrorCategory.TRANSIENT, ErrorCategory.THROTTLED]

    async def _backoff_delay(self, attempt: int) -> None:
        """Calculate and apply exponential backoff delay"""
        delay = min(
            self.retry_config.base_delay * (self.retry_config.backoff_factor ** attempt),
            self.retry_config.max_delay
        )

        if self.retry_config.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)

        self.logger.debug(f"Backing off for {delay:.2f}s before retry attempt {attempt + 1}")
        await asyncio.sleep(delay)

    def _update_metrics(self, provider_name: str, success: bool, duration: float) -> None:
        """Update provider performance metrics"""
        metrics = self.metrics[provider_name]
        current_time = time.time()

        metrics.total_time += duration

        if success:
            metrics.success_count += 1
            metrics.last_success = current_time
            metrics.consecutive_failures = 0
        else:
            metrics.failure_count += 1
            metrics.last_failure = current_time
            metrics.consecutive_failures += 1

    def _log_attempt(self, provider_name: str, attempt: int, duration: Optional[float] = None, error: Optional[Exception] = None) -> None:
        """Log provider attempt with structured data"""
        metrics = self.metrics[provider_name]

        log_data = {
            'provider': provider_name,
            'attempt': attempt,
            'success_rate': f"{metrics.success_rate:.2%}",
            'avg_response_time': f"{metrics.avg_response_time:.2f}s",
            'consecutive_failures': metrics.consecutive_failures
        }

        if duration is not None:
            log_data['duration'] = f"{duration:.2f}s"

        if error:
            error_category = self._classify_error(error, provider_name)
            log_data['error_category'] = error_category.value
            log_data['error'] = str(error)

            self.logger.warning(
                f"Provider {provider_name} failed (attempt {attempt}): {error}",
                extra=log_data
            )
        else:
            self.logger.info(
                f"Provider {provider_name} succeeded (attempt {attempt})",
                extra=log_data
            )

    async def _try_provider(self, provider_name: str, prompt: str) -> Tuple[str, Optional[ProviderError]]:
        """Try a single provider with retry logic"""
        provider = self.providers[provider_name]

        for attempt in range(self.retry_config.max_attempts):
            start_time = time.time()

            try:
                result = await provider.generate_video(prompt)
                duration = time.time() - start_time

                self._update_metrics(provider_name, True, duration)
                self._log_attempt(provider_name, attempt + 1, duration)

                return result, None

            except Exception as raw_error:
                duration = time.time() - start_time
                error_category = self._classify_error(raw_error, provider_name)

                provider_error = ProviderError(
                    f"Provider {provider_name} failed: {raw_error}",
                    error_category,
                    provider_name,
                    raw_error
                )

                self._update_metrics(provider_name, False, duration)
                self._log_attempt(provider_name, attempt + 1, duration, provider_error)

                # Don't retry for certain error types or on final attempt
                if not self._should_retry(error_category) or attempt == self.retry_config.max_attempts - 1:
                    return None, provider_error

                # Apply backoff before retry
                await self._backoff_delay(attempt)

        return None, provider_error

    def _get_fallback_order(self) -> List[str]:
        """Get deterministic provider fallback order based on recent performance"""
        # Sort providers by success rate, then by last success time
        def sort_key(provider_name: str) -> Tuple[float, float]:
            metrics = self.metrics[provider_name]
            return (
                -metrics.success_rate,  # Negative for descending order
                -(metrics.last_success or 0)  # Negative for descending order
            )

        return sorted(self.provider_order, key=sort_key)

    async def generate_video(self, prompt: str) -> str:
        """Generate video using provider fallback strategy"""
        self.logger.info(f"Starting video generation with prompt: {prompt[:100]}...")

        providers_to_try = self._get_fallback_order()
        errors = []

        for provider_name in providers_to_try:
            self.logger.info(f"Attempting provider: {provider_name}")

            result, error = await self._try_provider(provider_name, prompt)

            if result:
                self.logger.info(f"Successfully generated video using {provider_name}")
                return result

            if error:
                errors.append(error)

                # Skip to next provider for certain error types
                if error.category in [ErrorCategory.AUTH, ErrorCategory.PERMANENT]:
                    self.logger.warning(f"Skipping {provider_name} due to {error.category.value} error")
                    continue

        # All providers failed
        error_summary = "; ".join([f"{e.provider}: {e.category.value}" for e in errors])
        self.logger.error(f"All providers failed: {error_summary}")

        # Raise the last error or a summary
        if errors:
            raise errors[-1]
        else:
            raise ProviderError("No providers available", ErrorCategory.PERMANENT, "router")

    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status of all providers"""
        status = {
            'providers': {},
            'overall': {
                'healthy_providers': 0,
                'total_providers': len(self.providers)
            }
        }

        for provider_name, metrics in self.metrics.items():
            provider_healthy = metrics.consecutive_failures < 3

            status['providers'][provider_name] = {
                'healthy': provider_healthy,
                'success_rate': f"{metrics.success_rate:.2%}",
                'avg_response_time': f"{metrics.avg_response_time:.2f}s",
                'consecutive_failures': metrics.consecutive_failures,
                'total_requests': metrics.success_count + metrics.failure_count
            }

            if provider_healthy:
                status['overall']['healthy_providers'] += 1

        return status
