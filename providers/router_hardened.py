import time
import logging
import json
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass
from functools import wraps

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    AUTH = "auth"
    THROTTLED = "throttled"
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


@dataclass
class ProviderMetrics:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_time: float = 0.0
    avg_time: float = 0.0
    last_error: Optional[str] = None
    last_error_category: Optional[ErrorCategory] = None


class RetryConfig:
    def __init__(self, max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

    def get_delay(self, attempt: int) -> float:
        delay = self.base_delay * (2 ** attempt)
        return min(delay, self.max_delay)


class HardenedRouter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.providers = {}
        self.provider_metrics = {}
        self.retry_config = RetryConfig(
            max_attempts=config.get('retry_max_attempts', 3),
            base_delay=config.get('retry_base_delay', 1.0),
            max_delay=config.get('retry_max_delay', 30.0)
        )
        self._load_providers()

    def _load_providers(self):
        """Load and initialize provider instances"""
        if 'grok' in self.config:
            from .grok_provider import GrokProvider
            self.providers['grok'] = GrokProvider(self.config['grok'])
            self.provider_metrics['grok'] = ProviderMetrics()

        if 'runway' in self.config:
            from .runway_provider import RunwayProvider
            self.providers['runway'] = RunwayProvider(self.config['runway'])
            self.provider_metrics['runway'] = ProviderMetrics()

    def _classify_error(self, error: Exception, provider_name: str) -> ErrorCategory:
        """Classify errors into categories for appropriate handling"""
        error_str = str(error).lower()

        # Authentication errors
        if any(keyword in error_str for keyword in ['auth', 'api key', 'unauthorized', 'forbidden']):
            return ErrorCategory.AUTH

        # Rate limiting / throttling
        if any(keyword in error_str for keyword in ['rate limit', 'throttle', 'quota', 'too many requests']):
            return ErrorCategory.THROTTLED

        # Transient network/server errors
        if any(keyword in error_str for keyword in ['timeout', 'connection', 'network', 'server error', '500', '502', '503']):
            return ErrorCategory.TRANSIENT

        # Permanent errors (bad request, not found, etc)
        if any(keyword in error_str for keyword in ['bad request', '400', '404', 'not found', 'invalid']):
            return ErrorCategory.PERMANENT

        return ErrorCategory.UNKNOWN

    def _should_retry(self, error_category: ErrorCategory, attempt: int) -> bool:
        """Determine if we should retry based on error category and attempt count"""
        if attempt >= self.retry_config.max_attempts:
            return False

        # Retry transient errors and throttling
        if error_category in [ErrorCategory.TRANSIENT, ErrorCategory.THROTTLED, ErrorCategory.UNKNOWN]:
            return True

        # Don't retry auth or permanent errors
        return False

    def _update_metrics(self, provider_name: str, success: bool, duration: float, error: Optional[Exception] = None):
        """Update provider performance metrics"""
        metrics = self.provider_metrics[provider_name]
        metrics.attempts += 1
        metrics.total_time += duration
        metrics.avg_time = metrics.total_time / metrics.attempts

        if success:
            metrics.successes += 1
        else:
            metrics.failures += 1
            if error:
                metrics.last_error = str(error)
                metrics.last_error_category = self._classify_error(error, provider_name)

    def _log_attempt(self, provider_name: str, attempt: int, success: bool, duration: float, error: Optional[Exception] = None):
        """Log detailed attempt information"""
        metrics = self.provider_metrics[provider_name]

        if success:
            logger.info(f"Provider {provider_name} attempt {attempt}: SUCCESS (duration={duration:.2f}s, total_attempts={metrics.attempts}, success_rate={metrics.successes/metrics.attempts:.2f})")
        else:
            error_category = self._classify_error(error, provider_name) if error else ErrorCategory.UNKNOWN
            logger.warning(f"Provider {provider_name} attempt {attempt}: FAILED (duration={duration:.2f}s, error_category={error_category.value}, error={str(error)[:100]})")

    async def generate_with_provider(self, provider_name: str, prompt: str, **kwargs) -> Tuple[bool, Any, Optional[str]]:
        """Generate content with a specific provider, including retry logic"""
        if provider_name not in self.providers:
            return False, None, f"Provider {provider_name} not available"

        provider = self.providers[provider_name]

        for attempt in range(1, self.retry_config.max_attempts + 1):
            start_time = time.time()

            try:
                result = await provider.generate(prompt, **kwargs)
                duration = time.time() - start_time

                self._update_metrics(provider_name, True, duration)
                self._log_attempt(provider_name, attempt, True, duration)

                return True, result, None

            except Exception as error:
                duration = time.time() - start_time
                error_category = self._classify_error(error, provider_name)

                self._update_metrics(provider_name, False, duration, error)
                self._log_attempt(provider_name, attempt, False, duration, error)

                if not self._should_retry(error_category, attempt):
                    return False, None, f"{error_category.value}: {str(error)}"

                if attempt < self.retry_config.max_attempts:
                    delay = self.retry_config.get_delay(attempt - 1)
                    logger.info(f"Retrying {provider_name} in {delay:.1f}s (attempt {attempt + 1}/{self.retry_config.max_attempts})")
                    await asyncio.sleep(delay)

        return False, None, f"Max retries exceeded for {provider_name}"

    async def generate_with_fallback(self, prompt: str, preferred_provider: Optional[str] = None, **kwargs) -> Tuple[str, Any, List[str]]:
        """Generate content with fallback between providers"""
        providers_to_try = []
        errors = []

        # Try preferred provider first if specified
        if preferred_provider and preferred_provider in self.providers:
            providers_to_try.append(preferred_provider)

        # Add remaining providers
        for provider_name in self.providers.keys():
            if provider_name not in providers_to_try:
                providers_to_try.append(provider_name)

        logger.info(f"Attempting generation with provider order: {providers_to_try}")

        for provider_name in providers_to_try:
            success, result, error = await self.generate_with_provider(provider_name, prompt, **kwargs)

            if success:
                logger.info(f"Successfully generated content using {provider_name}")
                return provider_name, result, errors
            else:
                error_msg = f"{provider_name}: {error}"
                errors.append(error_msg)
                logger.warning(f"Provider {provider_name} failed: {error}")

        # All providers failed
        logger.error(f"All providers failed. Errors: {'; '.join(errors)}")
        raise Exception(f"All providers failed: {'; '.join(errors)}")

    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        """Get current status and metrics for all providers"""
        status = {}

        for provider_name, metrics in self.provider_metrics.items():
            status[provider_name] = {
                'available': provider_name in self.providers,
                'attempts': metrics.attempts,
                'successes': metrics.successes,
                'failures': metrics.failures,
                'success_rate': metrics.successes / max(metrics.attempts, 1),
                'avg_response_time': metrics.avg_time,
                'last_error': metrics.last_error,
                'last_error_category': metrics.last_error_category.value if metrics.last_error_category else None
            }

        return status

    def reset_metrics(self):
        """Reset all provider metrics"""
        for provider_name in self.provider_metrics:
            self.provider_metrics[provider_name] = ProviderMetrics()
        logger.info("Provider metrics reset")


# Async import handling
try:
    import asyncio
except ImportError:
    # Fallback for older Python versions
    import time as asyncio
    asyncio.sleep = time.sleep
