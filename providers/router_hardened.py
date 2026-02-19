"""
BoTTube Provider Router - Hardened version with retry, backoff, and observability.

Enhancements:
- Retry/backoff strategy for transient failures
- Structured error categories
- Timing and success/failure metrics
- Deterministic fallback behavior
"""

from __future__ import annotations

import functools
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from providers.base import GeneratedVideo
from providers.grok_imagine import GrokImagineProvider
from providers.runway import RunwayProvider

# Configure logging
logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Structured error categories for provider failures."""
    AUTH = "auth"                    # Authentication errors (API keys, permissions)
    THROTTLED = "throttled"          # Rate limiting, quota exceeded
    TRANSIENT = "transient"          # Network issues, timeouts, temporary failures
    PERMANENT = "permanent"          # Permanent errors (bad prompt, invalid params)
    UNKNOWN = "unknown"              # Uncategorized errors


@dataclass
class ProviderMetrics:
    """Metrics for a single provider attempt."""
    provider: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    success: bool = False
    error_category: Optional[ErrorCategory] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    
    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "provider": self.provider,
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "error_category": self.error_category.value if self.error_category else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }


@dataclass
class RouterMetrics:
    """Aggregated metrics for a router session."""
    prompt: str
    primary_provider: str
    fallback_used: bool = False
    total_attempts: int = 0
    provider_metrics: List[ProviderMetrics] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "prompt_preview": self.prompt[:50] + "..." if len(self.prompt) > 50 else self.prompt,
            "primary_provider": self.primary_provider,
            "fallback_used": self.fallback_used,
            "total_attempts": self.total_attempts,
            "total_duration_ms": sum(m.duration_ms for m in self.provider_metrics),
            "providers": [m.to_dict() for m in self.provider_metrics],
        }


class ProviderError(Exception):
    """Base exception for provider errors with categorization."""
    
    def __init__(self, message: str, category: ErrorCategory, provider: str):
        super().__init__(message)
        self.category = category
        self.provider = provider
        self.message = message
    
    def __str__(self) -> str:
        return f"[{self.provider}] {self.category.value}: {self.message}"


def categorize_error(error: Exception, provider: str) -> ProviderError:
    """
    Categorize an exception into a structured ProviderError.
    
    Args:
        error: The original exception
        provider: Provider name
        
    Returns:
        ProviderError with appropriate category
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()
    
    # Authentication errors
    auth_keywords = ["auth", "key", "token", "permission", "unauthorized", "forbidden"]
    if any(kw in error_str for kw in auth_keywords) or "auth" in error_type:
        return ProviderError(str(error), ErrorCategory.AUTH, provider)
    
    # Rate limiting / throttling
    throttle_keywords = ["rate", "limit", "throttle", "quota", "too many", "429"]
    if any(kw in error_str for kw in throttle_keywords):
        return ProviderError(str(error), ErrorCategory.THROTTLED, provider)
    
    # Transient network errors
    transient_keywords = [
        "timeout", "connection", "network", "temporarily", "unavailable",
        "503", "502", "504", "reset", "refused"
    ]
    transient_types = ["timeout", "connectionerror", "networkerror"]
    if any(kw in error_str for kw in transient_keywords) or any(t in error_type for t in transient_types):
        return ProviderError(str(error), ErrorCategory.TRANSIENT, provider)
    
    # Permanent errors (invalid input, etc.)
    permanent_keywords = ["invalid", "bad", "unsupported", "too large", "too long"]
    if any(kw in error_str for kw in permanent_keywords):
        return ProviderError(str(error), ErrorCategory.PERMANENT, provider)
    
    # Default to unknown
    return ProviderError(str(error), ErrorCategory.UNKNOWN, provider)


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    retryable_categories: Optional[set] = None,
) -> Callable:
    """
    Decorator that adds retry logic with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff calculation
        retryable_categories: Set of error categories that should trigger retry
        
    Returns:
        Decorated function
    """
    if retryable_categories is None:
        retryable_categories = {ErrorCategory.TRANSIENT, ErrorCategory.THROTTLED}
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error: Optional[Exception] = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except ProviderError as e:
                    last_error = e
                    
                    # Don't retry if error category is not retryable
                    if e.category not in retryable_categories:
                        logger.debug(f"Non-retryable error: {e}")
                        raise
                    
                    # Don't retry on last attempt
                    if attempt >= max_retries:
                        logger.debug(f"Max retries ({max_retries}) exceeded")
                        raise
                    
                    # Calculate backoff delay
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    
                    logger.info(
                        f"Attempt {attempt + 1}/{max_retries + 1} failed for {e.provider}: "
                        f"{e.category.value}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    
                except Exception as e:
                    # Unexpected error, don't retry
                    logger.exception(f"Unexpected error in {func.__name__}")
                    raise
            
            # Should never reach here, but just in case
            if last_error:
                raise last_error
            
        return wrapper
    return decorator


# Provider factory type
ProviderFactory = Callable[[], Any]

# Allow tests and future scripts to inject alternate providers.
_PROVIDER_FACTORIES: Dict[str, ProviderFactory] = {
    "grok": GrokImagineProvider,
    "runway": RunwayProvider,
}

RUNWAY_HINTS = (
    "runway",
    "cinematic",
    "film",
    "filmic",
    "high quality",
    "high-fidelity",
    "high fidelity",
    "photoreal",
    "photorealistic",
    "realistic",
    "physics",
    "professional",
)


def choose_provider(prompt: str, prefer: str = "auto") -> str:
    """Choose provider name from explicit preference or prompt hints."""
    normalized = (prefer or "auto").strip().lower()

    if normalized in {"grok", "runway"}:
        return normalized

    lowered = (prompt or "").lower()

    if "grok" in lowered:
        return "grok"

    if any(hint in lowered for hint in RUNWAY_HINTS):
        return "runway"

    return "grok"


@with_retry(max_retries=3, base_delay=1.0, max_delay=10.0)
def _generate_with_provider(
    provider_name: str,
    prompt: str,
    duration: int,
    **kwargs: Any,
) -> Tuple[GeneratedVideo, ProviderMetrics]:
    """
    Generate video with a single provider, with retry logic.
    
    Returns:
        Tuple of (GeneratedVideo, ProviderMetrics)
    """
    metrics = ProviderMetrics(provider=provider_name)
    
    try:
        provider = _PROVIDER_FACTORIES[provider_name]()
        result = provider.generate(prompt=prompt, duration=duration, **kwargs)
        
        metrics.end_time = time.time()
        metrics.success = True
        
        return result, metrics
        
    except Exception as exc:
        metrics.end_time = time.time()
        metrics.success = False
        
        # Categorize and re-raise as ProviderError
        provider_error = categorize_error(exc, provider_name)
        metrics.error_category = provider_error.category
        metrics.error_message = provider_error.message
        
        raise provider_error


def generate_video(
    prompt: str,
    *,
    prefer: str = "auto",
    fallback: bool = True,
    duration: int = 8,
    log_metrics: bool = True,
    **kwargs: Any,
) -> GeneratedVideo:
    """
    Generate video with selected provider and optional fallback.
    
    Enhancements:
    - Retry with exponential backoff for transient failures
    - Structured error categorization
    - Timing and success/failure metrics
    - Detailed logging
    
    Args:
        prompt: Video generation prompt
        prefer: Preferred provider ("auto", "grok", "runway")
        fallback: Whether to try fallback provider on failure
        duration: Video duration in seconds
        log_metrics: Whether to log metrics after generation
        **kwargs: Additional provider-specific arguments
        
    Returns:
        GeneratedVideo result
        
    Raises:
        RuntimeError: If all provider attempts fail
    """
    primary = choose_provider(prompt, prefer=prefer)
    attempts = [primary]

    if fallback:
        secondary = "runway" if primary == "grok" else "grok"
        attempts.append(secondary)

    # Initialize metrics
    router_metrics = RouterMetrics(
        prompt=prompt,
        primary_provider=primary,
        fallback_used=False,
    )

    errors: List[ProviderError] = []

    for idx, provider_name in enumerate(attempts):
        router_metrics.total_attempts += 1
        
        # Mark if we're using fallback
        if idx > 0:
            router_metrics.fallback_used = True
        
        try:
            logger.info(f"Attempting generation with {provider_name} (attempt {idx + 1}/{len(attempts)})")
            
            result, provider_metrics = _generate_with_provider(
                provider_name=provider_name,
                prompt=prompt,
                duration=duration,
                **kwargs,
            )
            
            router_metrics.provider_metrics.append(provider_metrics)
            
            # Add metadata to result
            result.metadata.setdefault("router_primary", primary)
            result.metadata.setdefault("router_provider", provider_name)
            result.metadata.setdefault("router_attempt", idx + 1)
            
            if router_metrics.fallback_used:
                result.metadata["router_fallback_used"] = True
            
            # Log success metrics
            if log_metrics:
                logger.info(f"Generation successful: {provider_metrics.to_dict()}")
                logger.info(f"Router metrics: {router_metrics.to_dict()}")
            
            return result
            
        except ProviderError as exc:
            errors.append(exc)
            
            # Create failed metrics entry
            failed_metrics = ProviderMetrics(
                provider=provider_name,
                success=False,
                error_category=exc.category,
                error_message=exc.message,
            )
            failed_metrics.end_time = time.time()
            router_metrics.provider_metrics.append(failed_metrics)
            
            logger.warning(f"Provider {provider_name} failed: {exc}")
            
            # Continue to next provider (fallback)
            continue

    # All attempts failed
    error_summary = "; ".join(
        f"{e.provider}[{e.category.value}]: {e.message}" for e in errors
    )
    
    if log_metrics:
        logger.error(f"All providers failed. Router metrics: {router_metrics.to_dict()}")
    
    raise RuntimeError(f"All provider attempts failed ({error_summary})")


def get_provider_status() -> Dict[str, Dict[str, Any]]:
    """
    Get status information for all providers.
    
    Returns:
        Dictionary mapping provider names to status info
    """
    status = {}
    
    for name, factory in _PROVIDER_FACTORIES.items():
        try:
            provider = factory()
            status[name] = {
                "available": True,
                "name": name,
                # Could add more provider-specific status here
            }
        except Exception as e:
            status[name] = {
                "available": False,
                "name": name,
                "error": str(e),
            }
    
    return status
