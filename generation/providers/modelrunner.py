# SPDX-License-Identifier: MIT
"""
ModelRunner provider
====================
Queue-based: submit -> poll status -> download result.
Activate by setting MODELRUNNER_KEY in environment.

The endpoint is configurable with MODELRUNNER_VIDEO_MODEL, so this one adapter
covers any text-to-video model in the catalog without a code change.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Optional, Tuple

from generation.models import GenerationMode, GenerationRequest
from generation.provider import GenerationProvider, ProviderCapabilities

log = logging.getLogger("generation.providers.modelrunner")

MODELRUNNER_KEY = os.environ.get("MODELRUNNER_KEY", "")
MODELRUNNER_MODEL = os.environ.get(
    "MODELRUNNER_VIDEO_MODEL", "wan-video/wan/v3.0/text-to-video"
)
MODELRUNNER_QUEUE_URL = "https://queue.modelrunner.run"

# Model accepts 2-30s; the router may ask for more, so requests are clamped.
MIN_DURATION = 2
MAX_DURATION = 30

VIDEO_WIDTH = 720
VIDEO_HEIGHT = 720


def _headers() -> dict:
    """Auth + content headers for every call to the queue API."""
    return {
        "Authorization": f"Key {MODELRUNNER_KEY}",
        "Content-Type": "application/json",
    }


class ModelRunnerProvider(GenerationProvider):

    def get_name(self) -> str:
        """Return this provider's registry key."""
        return "modelrunner"

    def get_capabilities(self) -> ProviderCapabilities:
        """Describe what this provider supports (modes, limits, cost/quality tier, availability)."""
        return ProviderCapabilities(
            name="modelrunner",
            modes=[GenerationMode.text_to_video],
            max_duration=MAX_DURATION,
            max_resolution=(1280, 720),
            # The model returns a native soundtrack, but the shared re-encode
            # step replaces audio with a silent track for every provider, so
            # audio is switched off at submit time rather than paid for and
            # discarded.
            supports_audio=False,
            supports_captions=False,
            estimated_latency_s=90.0,
            quality_tier=4,
            # A paid API with no free tier, unlike the free-tier backends above.
            cost_tier=3,
            requires_api_key=True,
            available=bool(MODELRUNNER_KEY),
        )

    def validate_input(self, req: GenerationRequest) -> Tuple[bool, str]:
        """Check the request has a prompt and the API key is configured before submitting."""
        if not req.prompt:
            return False, "prompt is required"
        if not MODELRUNNER_KEY:
            return False, "MODELRUNNER_KEY not configured"
        return True, ""

    def submit(self, req: GenerationRequest, output_dir: Path) -> Tuple[bool, str]:
        """Enqueue a generation job on ModelRunner; returns (ok, request_id_or_error)."""
        duration = max(MIN_DURATION, min(req.duration, MAX_DURATION))
        payload = json.dumps({
            "prompt": req.prompt,
            "duration": duration,
            "resolution": "720P",
            "aspect_ratio": "1:1",
            "audio": False,
        }).encode()

        try:
            http_req = urllib.request.Request(
                f"{MODELRUNNER_QUEUE_URL}/{MODELRUNNER_MODEL}",
                data=payload,
                headers=_headers(),
            )
            with urllib.request.urlopen(http_req, timeout=15) as resp:
                result = json.loads(resp.read())

            request_id = result.get("request_id", "")
            if not request_id:
                return False, "no request_id returned"
            return True, request_id
        except Exception as exc:
            return False, str(exc)

    def get_status(self, external_id: str) -> Tuple[str, float]:
        """Poll the queue for a job's status; returns (status_label, progress_fraction)."""
        status_url = (
            f"{MODELRUNNER_QUEUE_URL}/{MODELRUNNER_MODEL}"
            f"/requests/{external_id}/status"
        )
        try:
            req = urllib.request.Request(status_url, headers=_headers())
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            status = data.get("status", "IN_QUEUE")
            if status == "COMPLETED":
                return "completed", 1.0
            if status in ("FAILED", "CANCELLED"):
                return "failed", 0.0
            if status == "IN_PROGRESS":
                return "running", 0.5
            return "pending", 0.0
        except Exception:
            return "pending", 0.0

    def get_result(self, external_id: str, output_dir: Path) -> Optional[Path]:
        """Download a completed job's video and re-encode it to the standard output format."""
        result_url = (
            f"{MODELRUNNER_QUEUE_URL}/{MODELRUNNER_MODEL}/requests/{external_id}"
        )
        try:
            req = urllib.request.Request(result_url, headers=_headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                final = json.loads(resp.read())

            video_url = _extract_video_url(final.get("output"))
            if not video_url:
                return None

            raw_path = output_dir / f"modelrunner_raw_{uuid.uuid4().hex[:8]}.mp4"
            out_path = output_dir / f"modelrunner_{uuid.uuid4().hex[:8]}.mp4"
            urllib.request.urlretrieve(video_url, str(raw_path))

            # Re-encode to standard format
            cmd = [
                "ffmpeg", "-y", "-i", str(raw_path),
                "-vf", (
                    f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
                    f":force_original_aspect_ratio=decrease,"
                    f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x1a1a2e"
                ),
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:a", "aac", "-shortest",
                str(out_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=60, check=False)
            raw_path.unlink(missing_ok=True)
            return out_path if out_path.exists() else None
        except Exception as exc:
            log.warning("ModelRunner result download failed: %s", exc)
            return None

    def cancel(self, external_id: str) -> bool:
        """Request cancellation of a queued/running job; returns True if the call succeeded."""
        cancel_url = (
            f"{MODELRUNNER_QUEUE_URL}/{MODELRUNNER_MODEL}"
            f"/requests/{external_id}/cancel"
        )
        try:
            req = urllib.request.Request(
                cancel_url, method="PUT", headers=_headers()
            )
            urllib.request.urlopen(req, timeout=10)
            return True
        except Exception:
            return False


def _extract_video_url(output) -> str:
    """Pull the video URL out of a completed request's output.

    Output shape is defined by the model, not the platform: most video models
    return the URL as a bare string, others wrap it in an object. Handling both
    is what lets MODELRUNNER_VIDEO_MODEL point at any of them.
    """
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for key in ("video_url", "url", "video", "output"):
            value = output.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                nested = value.get("url")
                if isinstance(nested, str) and nested:
                    return nested
    if isinstance(output, list) and output:
        return _extract_video_url(output[0])
    return ""
