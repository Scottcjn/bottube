"""
fal.ai SVD-LCM provider (skeleton)
====================================
Queue-based: submit -> poll status -> download result.
Activate by setting FAL_API_KEY in environment.
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

log = logging.getLogger("generation.providers.fal_ai")

FAL_API_KEY = os.environ.get("FAL_API_KEY", "")
FAL_VIDEO_URL = "https://queue.fal.run/fal-ai/fast-svd-lcm"
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 720


class FalAIProvider(GenerationProvider):

    def get_name(self) -> str:
        return "fal_ai"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="fal_ai",
            modes=[GenerationMode.text_to_video, GenerationMode.image_to_video],
            max_duration=8,
            max_resolution=(512, 512),
            supports_audio=False,
            supports_captions=False,
            estimated_latency_s=45.0,
            quality_tier=3,
            cost_tier=1,
            requires_api_key=True,
            available=bool(FAL_API_KEY),
        )

    def validate_input(self, req: GenerationRequest) -> Tuple[bool, str]:
        if not req.prompt:
            return False, "prompt is required"
        if not FAL_API_KEY:
            return False, "FAL_API_KEY not configured"
        return True, ""

    def submit(self, req: GenerationRequest, output_dir: Path) -> Tuple[bool, str]:
        payload = json.dumps({
            "prompt": req.prompt,
            "num_frames": min(req.duration * 8, 64),
            "fps": 8,
            "motion_bucket_id": 127,
        }).encode()

        try:
            http_req = urllib.request.Request(
                FAL_VIDEO_URL,
                data=payload,
                headers={
                    "Authorization": f"Key {FAL_API_KEY}",
                    "Content-Type": "application/json",
                },
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
        status_url = (
            f"https://queue.fal.run/fal-ai/fast-svd-lcm"
            f"/requests/{external_id}/status"
        )
        try:
            req = urllib.request.Request(
                status_url,
                headers={"Authorization": f"Key {FAL_API_KEY}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            status = data.get("status", "PENDING")
            if status == "COMPLETED":
                return "completed", 1.0
            elif status == "FAILED":
                return "failed", 0.0
            return "running", 0.5
        except Exception:
            return "pending", 0.0

    def get_result(self, external_id: str, output_dir: Path) -> Optional[Path]:
        result_url = (
            f"https://queue.fal.run/fal-ai/fast-svd-lcm"
            f"/requests/{external_id}"
        )
        try:
            req = urllib.request.Request(
                result_url,
                headers={"Authorization": f"Key {FAL_API_KEY}"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                final = json.loads(resp.read())

            video_url = final.get("video", {}).get("url", "")
            if not video_url:
                return None

            raw_path = output_dir / f"fal_raw_{uuid.uuid4().hex[:8]}.mp4"
            out_path = output_dir / f"fal_{uuid.uuid4().hex[:8]}.mp4"
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
            log.warning("fal.ai result download failed: %s", exc)
            return None

    def cancel(self, external_id: str) -> bool:
        cancel_url = (
            f"https://queue.fal.run/fal-ai/fast-svd-lcm"
            f"/requests/{external_id}/cancel"
        )
        try:
            req = urllib.request.Request(
                cancel_url,
                method="PUT",
                headers={"Authorization": f"Key {FAL_API_KEY}"},
            )
            urllib.request.urlopen(req, timeout=10)
            return True
        except Exception:
            return False
