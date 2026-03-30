"""
generation/provider.py - Provider adapter interface and registry
================================================================
Each video-generation backend implements GenerationProvider.
The ProviderRegistry holds all registered adapters so the router
can query capabilities at routing time.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from generation.models import GenerationMode, GenerationRequest

log = logging.getLogger("generation.provider")


# ---------------------------------------------------------------------------
# Capability descriptor
# ---------------------------------------------------------------------------

@dataclass
class ProviderCapabilities:
    """What a provider can do, used by the router for scoring."""
    name: str
    modes: List[GenerationMode] = field(default_factory=list)
    max_duration: int = 8                # seconds
    max_resolution: Tuple[int, int] = (720, 720)
    supports_audio: bool = False
    supports_captions: bool = False
    estimated_latency_s: float = 30.0    # typical wall-clock time
    quality_tier: int = 3                # 1=low ... 5=best
    cost_tier: int = 1                   # 1=free ... 5=expensive
    requires_api_key: bool = False
    available: bool = True               # dynamically toggled
    styles: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class GenerationProvider(ABC):
    """Interface every backend must implement."""

    @abstractmethod
    def get_name(self) -> str:
        """Unique short name, e.g. 'comfyui_ltx'."""

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Return current capabilities (may change at runtime)."""

    @abstractmethod
    def validate_input(self, req: GenerationRequest) -> Tuple[bool, str]:
        """Return (ok, reason).  Check prompt length, mode support, etc."""

    @abstractmethod
    def submit(self, req: GenerationRequest, output_dir: Path) -> Tuple[bool, str]:
        """Start generation.  Return (ok, external_job_id_or_path).

        For synchronous providers the second element is a local file path.
        For async providers it is an opaque job id to pass to get_status().
        """

    @abstractmethod
    def get_status(self, external_id: str) -> Tuple[str, float]:
        """Return (status_str, progress_0_to_1).
        status_str in {"pending", "running", "completed", "failed"}.
        Synchronous providers can just return ("completed", 1.0).
        """

    @abstractmethod
    def get_result(self, external_id: str, output_dir: Path) -> Optional[Path]:
        """Download / locate the finished artifact.  Return local Path or None."""

    def cancel(self, external_id: str) -> bool:
        """Best-effort cancel.  Default is no-op (returns False)."""
        return False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """Thread-safe registry of provider adapters."""

    def __init__(self):
        self._providers: Dict[str, GenerationProvider] = {}

    def register(self, provider: GenerationProvider):
        name = provider.get_name()
        self._providers[name] = provider
        log.info("Registered provider: %s", name)

    def get(self, name: str) -> Optional[GenerationProvider]:
        return self._providers.get(name)

    def list_available(self) -> List[GenerationProvider]:
        """Return providers whose capabilities say available=True."""
        return [
            p for p in self._providers.values()
            if p.get_capabilities().available
        ]

    def list_all(self) -> List[GenerationProvider]:
        return list(self._providers.values())

    def names(self) -> List[str]:
        return list(self._providers.keys())
