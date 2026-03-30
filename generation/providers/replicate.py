"""
Replicate provider (skeleton)
===============================
Queue-based: create prediction -> poll -> download.
Activate by setting REPLICATE_API_TOKEN in environment.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.request
import uuid
from pathlib import Path
from typing import Optional, Tuple

from generation.models import GenerationMode, GenerationRequest
from generation.provider import GenerationProvider, ProviderCapabilities

log = logging.getLogger("generation.providers.replicate")

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")
REPLICATE_VIDEO_URL = "https://api.replicate.com/v1/predictions"
# Default model version (zeroscope v2)
REPLICATE_MODEL_VERSION = os.environ.get(
    "REPLICATE_MODEL_VERSION",
    "3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
)
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 720


class ReplicateProvider(GenerationProvider):

    def get_name(self) -> str:
        return "replicate"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="replicate",
            modes=[GenerationMode.text_to_video],
            max_duration=8,
            max_resolution=(512, 512),
            supports_audio=False,
            supports_captions=False,
            estimated_latency_s=120.0,
            quality_tier=3,
            cost_tier=2,
            requires_api_key=True,
            available=bool(REPLICATE_API_TOKEN),
        )

    def validate_input(self, req: GenerationRequest) -> Tuple[bool, str]:
        if not req.prompt:
            return False, "prompt is required"
        if not REPLICATE_API_TOKEN:
            return False, "REPLICATE_API_TOKEN not configured"
        return True, ""

    def submit(self, req: GenerationRequest, output_dir: Path) -> Tuple[bool, str]:
        payload = json.dumps({
            "version": REPLICATE_MODEL_VERSION,
            "input": {
                "prompt": req.prompt,
                "num_frames": min(req.duration * 8, 64),
                "fps": 8,
                "width": 512,
                "height": 512,
            },
        }).encode()

        try:
            http_req = urllib.request.Request(
                REPLICATE_VIDEO_URL,
                data=payload,
                headers={
                    "Authorization": f"Token {REPLICATE_API_TOKEN}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(http_req, timeout=15) as resp:
                result = json.loads(resp.read())

            poll_url = result.get("urls", {}).get("get", "")
            if not poll_url:
                return False, "no poll url returned"
            # Store poll_url as external_id
            return True, poll_url
        except Exception as exc:
            return False, str(exc)

    def get_status(self, external_id: str) -> Tuple[str, float]:
        """external_id is the Replicate poll URL."""
        try:
            req = urllib.request.Request(
                external_id,
                headers={"Authorization": f"Token {REPLICATE_API_TOKEN}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            status = data.get("status", "starting")
            if status == "succeeded":
                return "completed", 1.0
            elif status == "failed":
                return "failed", 0.0
            elif status == "canceled":
                return "failed", 0.0
            return "running", 0.5
        except Exception:
            return "pending", 0.0

    def get_result(self, external_id: str, output_dir: Path) -> Optional[Path]:
        try:
            req = urllib.request.Request(
                external_id,
                headers={"Authorization": f"Token {REPLICATE_API_TOKEN}"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())

            output_url = data.get("output", "")
            if isinstance(output_url, list):
                output_url = output_url[0] if output_url else ""
            if not output_url:
                return None

            raw_path = output_dir / f"replicate_raw_{uuid.uuid4().hex[:8]}.mp4"
            out_path = output_dir / f"replicate_{uuid.uuid4().hex[:8]}.mp4"
            urllib.request.urlretrieve(output_url, str(raw_path))

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
            log.warning("Replicate result download failed: %s", exc)
            return None

    def cancel(self, external_id: str) -> bool:
        try:
            cancel_url = external_id + "/cancel"
            req = urllib.request.Request(
                cancel_url,
                method="POST",
                headers={"Authorization": f"Token {REPLICATE_API_TOKEN}"},
            )
            urllib.request.urlopen(req, timeout=10)
            return True
        except Exception:
            return False
