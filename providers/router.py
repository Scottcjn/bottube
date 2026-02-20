from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Tuple

from providers.base import GeneratedVideo
from providers.grok_imagine import GrokImagineProvider
from providers.runway import RunwayProvider

ProviderFactory = Callable[[], Any]

# Allow tests and future scripts to inject alternate providers.
_PROVIDER_FACTORIES: Dict[str, ProviderFactory] = {
    "grok": GrokImagineProvider,
    "runway": RunwayProvider,
}
_PROVIDER_FAILURE_STREAK: Dict[str, int] = {"grok": 0, "runway": 0}
_FAILURE_ALERT_THRESHOLD = 3
_LOGGER = logging.getLogger(__name__)

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


def classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if any(x in msg for x in ("401", "403", "unauthorized", "forbidden", "api key", "invalid token", "auth")):
        return "auth"
    if any(x in msg for x in ("429", "rate limit", "throttle", "quota")):
        return "throttled"
    if any(
        x in msg
        for x in (
            "timeout",
            "timed out",
            "temporarily unavailable",
            "connection",
            "network",
            "503",
            "502",
            "500",
            "504",
        )
    ):
        return "transient"
    if any(x in msg for x in ("400", "404", "invalid", "bad request", "unsupported", "requires an image")):
        return "permanent"
    return "unknown"


def _should_retry(category: str) -> bool:
    return category in {"transient", "throttled"}


def _backoff_seconds(retry_idx: int, base_seconds: float, cap_seconds: float = 10.0) -> float:
    return min(float(cap_seconds), float(base_seconds) * (2 ** retry_idx))


def _record_provider_failure(provider_name: str) -> None:
    current = int(_PROVIDER_FAILURE_STREAK.get(provider_name, 0)) + 1
    _PROVIDER_FAILURE_STREAK[provider_name] = current
    if current >= _FAILURE_ALERT_THRESHOLD:
        _LOGGER.warning(
            "Provider '%s' has failed %d consecutive router runs",
            provider_name,
            current,
        )


def _record_provider_success(provider_name: str) -> None:
    _PROVIDER_FAILURE_STREAK[provider_name] = 0


def generate_video(
    prompt: str,
    *,
    prefer: str = "auto",
    fallback: bool = True,
    duration: int = 8,
    max_retries: int = 2,
    retry_backoff_s: float = 1.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> GeneratedVideo:
    """Generate with selected provider and optional fallback."""
    primary = choose_provider(prompt, prefer=prefer)
    attempts = [primary]

    if fallback:
        secondary = "runway" if primary == "grok" else "grok"
        attempts.append(secondary)

    errors: List[Tuple[str, str, str]] = []
    attempt_metrics: List[Dict[str, Any]] = []
    category_totals: Dict[str, int] = {}
    provider_time_ms: Dict[str, int] = {}
    retries_per_provider = max(0, int(max_retries))
    base_backoff = max(0.0, float(retry_backoff_s))

    for provider_name in attempts:
        provider = _PROVIDER_FACTORIES[provider_name]()
        final_failure_for_provider = False
        for retry_idx in range(retries_per_provider + 1):
            started = time.perf_counter()
            try:
                result = provider.generate(prompt=prompt, duration=duration, **kwargs)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                provider_time_ms[provider_name] = provider_time_ms.get(provider_name, 0) + elapsed_ms
                _record_provider_success(provider_name)

                attempt_metrics.append(
                    {
                        "provider": provider_name,
                        "status": "ok",
                        "retry_index": retry_idx,
                        "duration_ms": elapsed_ms,
                    }
                )

                result.metadata.setdefault("router_primary", primary)
                result.metadata.setdefault("router_provider", provider_name)
                result.metadata.setdefault("router_attempts", attempt_metrics)
                result.metadata.setdefault("router_provider_time_ms", provider_time_ms)
                result.metadata.setdefault("router_error_categories", category_totals)
                result.metadata.setdefault("router_fallback_used", provider_name != primary)
                return result
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                provider_time_ms[provider_name] = provider_time_ms.get(provider_name, 0) + elapsed_ms
                category = classify_error(exc)
                category_totals[category] = int(category_totals.get(category, 0)) + 1
                errors.append((provider_name, category, str(exc)))
                attempt_metrics.append(
                    {
                        "provider": provider_name,
                        "status": "error",
                        "retry_index": retry_idx,
                        "duration_ms": elapsed_ms,
                        "category": category,
                        "error": str(exc),
                    }
                )
                should_retry = _should_retry(category) and retry_idx < retries_per_provider
                if should_retry:
                    delay = _backoff_seconds(retry_idx, base_backoff)
                    if delay > 0:
                        sleep_fn(delay)
                    continue
                final_failure_for_provider = True
                break
        if final_failure_for_provider:
            _record_provider_failure(provider_name)

    error_text = "; ".join(f"{name}/{category}: {message}" for name, category, message in errors)
    raise RuntimeError(f"All provider attempts failed ({error_text})")
