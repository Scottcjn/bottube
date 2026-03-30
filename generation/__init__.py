"""
BoTTube Multi-Provider Video Generation Router
===============================================
Replaces the monolithic video_gen_blueprint with a modular, provider-based
architecture supporting fallback chains, quality gating, and background
job processing.

Providers (in priority order):
  1. ComfyUI/LTX-2 (local GPU via Tailscale)
  2. HuggingFace Inference API
  3. Google Gemini (image + Ken Burns)
  4. Stability AI (image + Ken Burns)
  5. fal.ai (SVD-LCM)
  6. Replicate
  7. FFmpeg title card (always-works fallback)
"""

from generation.models import (
    GenerationRequest,
    InternalJob,
    JobStatus,
    GenerationMode,
)
from generation.provider import ProviderRegistry
from generation.router import GenerationRouter

__all__ = [
    "GenerationRequest",
    "InternalJob",
    "JobStatus",
    "GenerationMode",
    "ProviderRegistry",
    "GenerationRouter",
]
