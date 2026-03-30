"""
generation/router.py - Smart routing with scoring and fallback chains
=====================================================================
Scoring formula:
  capability_match * 100
  + quality_tier * 25
  + availability * 20
  - cost_tier * 10
  - latency * 5
  + hint_bonus (50 if provider matches provider_hint)

Routing modes:
  fast         - minimise latency (latency weight x3)
  quality      - maximise quality (quality weight x3)
  experimental - prefer less-used providers (bonus for low usage)
  safe         - only providers with quality_tier >= 3
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from generation.models import GenerationMode, GenerationRequest
from generation.provider import GenerationProvider, ProviderRegistry

log = logging.getLogger("generation.router")


@dataclass
class RoutingDecision:
    """Result of the routing process."""
    provider: str
    fallback_chain: List[str] = field(default_factory=list)
    reason: str = ""
    scores: Dict[str, float] = field(default_factory=dict)


class GenerationRouter:
    """Select the best provider for a given GenerationRequest."""

    # Track recent provider usage for load-balancing / experimental mode
    _usage_counts: Dict[str, int] = {}
    _last_reset: float = 0.0

    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def route(
        self,
        req: GenerationRequest,
        mode: str = "quality",
    ) -> RoutingDecision:
        """Score every available provider and return the best + fallback chain."""
        self._maybe_reset_usage()

        candidates = self.registry.list_available()
        if not candidates:
            return RoutingDecision(
                provider="ffmpeg_titlecard",
                fallback_chain=[],
                reason="no_providers_available",
            )

        scored: List[tuple] = []
        all_scores: Dict[str, float] = {}

        for prov in candidates:
            score = self._score(prov, req, mode)
            all_scores[prov.get_name()] = score
            scored.append((score, prov.get_name()))

        scored.sort(key=lambda x: x[0], reverse=True)

        best_name = scored[0][1]
        fallbacks = [name for _, name in scored[1:] if _ > 0]

        # Always ensure ffmpeg_titlecard is in fallback chain as last resort
        if "ffmpeg_titlecard" not in fallbacks and best_name != "ffmpeg_titlecard":
            fallbacks.append("ffmpeg_titlecard")

        self._record_usage(best_name)

        return RoutingDecision(
            provider=best_name,
            fallback_chain=fallbacks,
            reason=f"mode={mode}, top_score={scored[0][0]:.1f}",
            scores=all_scores,
        )

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score(
        self,
        prov: GenerationProvider,
        req: GenerationRequest,
        mode: str,
    ) -> float:
        caps = prov.get_capabilities()
        score = 0.0

        # --- Capability match (hard filter) ---
        if req.mode not in caps.modes:
            return -1000.0  # cannot handle this mode at all

        ok, _ = prov.validate_input(req)
        if not ok:
            return -500.0

        score += 100.0  # base capability match

        # --- Quality ---
        q_weight = 75.0 if mode == "quality" else 25.0
        score += caps.quality_tier * q_weight

        # --- Availability ---
        score += 20.0 if caps.available else 0.0

        # --- Cost ---
        c_weight = 10.0
        score -= caps.cost_tier * c_weight

        # --- Latency ---
        l_weight = 15.0 if mode == "fast" else 5.0
        # Normalise: 10s -> 0 penalty, 300s -> full penalty
        latency_penalty = min(caps.estimated_latency_s / 60.0, 5.0)
        score -= latency_penalty * l_weight

        # --- Provider hint bonus ---
        if req.provider_hint and req.provider_hint.lower() in prov.get_name().lower():
            score += 50.0

        # --- Safe mode filter ---
        if mode == "safe" and caps.quality_tier < 3:
            score -= 200.0

        # --- Experimental mode: favour less-used ---
        if mode == "experimental":
            usage = self._usage_counts.get(prov.get_name(), 0)
            score += max(0, 30 - usage * 5)

        # --- Duration check ---
        if req.duration > caps.max_duration:
            score -= 50.0  # penalise but don't disqualify

        # --- Style match ---
        if req.style and caps.styles:
            if req.style.lower() in [s.lower() for s in caps.styles]:
                score += 15.0

        return score

    # ------------------------------------------------------------------
    # Usage tracking (simple in-memory, resets every hour)
    # ------------------------------------------------------------------

    def _maybe_reset_usage(self):
        now = time.time()
        if now - self._last_reset > 3600:
            self._usage_counts.clear()
            self._last_reset = now

    def _record_usage(self, name: str):
        self._usage_counts[name] = self._usage_counts.get(name, 0) + 1
