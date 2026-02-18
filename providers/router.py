from __future__ import annotations

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


def generate_video(
    prompt: str,
    *,
    prefer: str = "auto",
    fallback: bool = True,
    duration: int = 8,
    **kwargs: Any,
) -> GeneratedVideo:
    """Generate with selected provider and optional fallback."""
    primary = choose_provider(prompt, prefer=prefer)
    attempts = [primary]

    if fallback:
        secondary = "runway" if primary == "grok" else "grok"
        attempts.append(secondary)

    errors: List[Tuple[str, str]] = []

    for provider_name in attempts:
        try:
            provider = _PROVIDER_FACTORIES[provider_name]()
            result = provider.generate(prompt=prompt, duration=duration, **kwargs)
            result.metadata.setdefault("router_primary", primary)
            result.metadata.setdefault("router_provider", provider_name)
            if provider_name != primary:
                result.metadata["router_fallback_used"] = True
            return result
        except Exception as exc:
            errors.append((provider_name, str(exc)))

    error_text = "; ".join(f"{name}: {message}" for name, message in errors)
    raise RuntimeError(f"All provider attempts failed ({error_text})")
