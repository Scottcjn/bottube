# SPDX-License-Identifier: MIT
"""
generation/reliability.py - retry, error classification and provider metrics
===========================================================================
Small, dependency-free helpers used by the generation worker.  The goal is to
make provider fallback deterministic and observable without changing provider
adapter APIs.
"""
from __future__ import annotations

import logging
import random
import socket
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple, TypeVar

log = logging.getLogger("generation.reliability")

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff policy for transient provider failures."""

    attempts: int = 3
    base_delay_s: float = 0.5
    max_delay_s: float = 4.0
    jitter_s: float = 0.2

    def delay_for(self, attempt_index: int) -> float:
        delay = min(self.max_delay_s, self.base_delay_s * (2 ** max(0, attempt_index)))
        if self.jitter_s:
            delay += random.uniform(0.0, self.jitter_s)
        return delay


@dataclass
class ProviderMetrics:
    """In-memory counters and timings for provider attempts."""

    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_s: float = 0.0
    error_categories: Dict[str, int] = field(default_factory=dict)

    @property
    def avg_latency_s(self) -> float:
        return self.total_latency_s / self.attempts if self.attempts else 0.0

    def to_dict(self) -> dict:
        return {
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "avg_latency_s": round(self.avg_latency_s, 3),
            "total_latency_s": round(self.total_latency_s, 3),
            "error_categories": dict(self.error_categories),
        }


_PROVIDER_METRICS: Dict[str, ProviderMetrics] = {}


def classify_error(error: object) -> str:
    """Classify provider errors for retry/fallback decisions and CLI output."""
    text = str(error or "").lower()
    if any(token in text for token in ("401", "403", "unauthorized", "forbidden", "api key", "auth")):
        return "auth"
    if any(token in text for token in ("429", "rate limit", "quota", "throttl", "too many")):
        return "throttled"
    if isinstance(error, (TimeoutError, socket.timeout)) or any(
        token in text for token in ("timeout", "timed out", "temporar", "connection reset", "network", "unavailable", "502", "503", "504")
    ):
        return "transient"
    return "permanent"


def is_retryable(category: str) -> bool:
    return category in {"transient", "throttled"}


def record_provider_metric(provider: str, *, success: bool, latency_s: float, category: Optional[str] = None) -> dict:
    metrics = _PROVIDER_METRICS.setdefault(provider, ProviderMetrics())
    metrics.attempts += 1
    metrics.total_latency_s += max(0.0, latency_s)
    if success:
        metrics.successes += 1
    else:
        metrics.failures += 1
        if category:
            metrics.error_categories[category] = metrics.error_categories.get(category, 0) + 1
    return metrics.to_dict()


def provider_metrics_snapshot() -> Dict[str, dict]:
    return {name: metrics.to_dict() for name, metrics in _PROVIDER_METRICS.items()}


def run_with_retries(provider: str, operation: str, func: Callable[[], T], policy: RetryPolicy = RetryPolicy()) -> Tuple[bool, Optional[T], str, float, int]:
    """Run a provider operation with bounded retries for transient categories.

    Returns: (ok, value, category_or_ok, total_latency_s, attempts_used)
    """
    start = time.monotonic()
    last_category = "permanent"
    attempts = max(1, policy.attempts)
    for attempt_index in range(attempts):
        try:
            value = func()
            latency = time.monotonic() - start
            record_provider_metric(provider, success=True, latency_s=latency)
            log.info(
                "provider_attempt provider=%s operation=%s attempt=%d success=true latency_s=%.3f",
                provider, operation, attempt_index + 1, latency,
            )
            return True, value, "ok", latency, attempt_index + 1
        except Exception as exc:  # provider adapters vary; normalize here
            last_category = classify_error(exc)
            retry = attempt_index + 1 < attempts and is_retryable(last_category)
            log.warning(
                "provider_attempt provider=%s operation=%s attempt=%d success=false category=%s retry=%s error=%s",
                provider, operation, attempt_index + 1, last_category, retry, str(exc)[:300],
            )
            if not retry:
                latency = time.monotonic() - start
                record_provider_metric(provider, success=False, latency_s=latency, category=last_category)
                return False, None, last_category, latency, attempt_index + 1
            time.sleep(policy.delay_for(attempt_index))

    latency = time.monotonic() - start
    record_provider_metric(provider, success=False, latency_s=latency, category=last_category)
    return False, None, last_category, latency, attempts
