"""
Stability AI provider (skeleton)
=================================
Generates image via Stable Image Core, then animates with Ken Burns zoom.
Activate by setting STABILITY_API_KEY in environment.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Tuple

import urllib.request

from generation.models import GenerationMode, GenerationRequest
from generation.provider import GenerationProvider, ProviderCapabilities

log = logging.getLogger("generation.providers.stability")

STABILITY_API_KEY = os.environ.get("STABILITY_API_KEY", "")
STABILITY_IMG_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 720


class StabilityProvider(GenerationProvider):

    def get_name(self) -> str:
        return "stability"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="stability",
            modes=[GenerationMode.text_to_video, GenerationMode.text_to_image_sequence],
            max_duration=15,
            max_resolution=(1024, 1024),
            supports_audio=False,
            supports_captions=False,
            estimated_latency_s=25.0,
            quality_tier=4,
            cost_tier=2,
            requires_api_key=True,
            available=bool(STABILITY_API_KEY),
            styles=["photorealistic", "anime", "digital_art", "3d_model"],
        )

    def validate_input(self, req: GenerationRequest) -> Tuple[bool, str]:
        if not req.prompt:
            return False, "prompt is required"
        if not STABILITY_API_KEY:
            return False, "STABILITY_API_KEY not configured"
        return True, ""

    def submit(self, req: GenerationRequest, output_dir: Path) -> Tuple[bool, str]:
        # Step 1: Generate image via Stable Image Core
        boundary = "----FormBoundary" + uuid.uuid4().hex[:16]
        body_parts = []
        for name, value in [("prompt", req.prompt), ("output_format", "png"),
                            ("aspect_ratio", "1:1")]:
            body_parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{name}"\r\n\r\n{value}'
            )
        body = "\r\n".join(body_parts) + f"\r\n--{boundary}--\r\n"

        try:
            http_req = urllib.request.Request(
                STABILITY_IMG_URL,
                data=body.encode(),
                headers={
                    "Authorization": f"Bearer {STABILITY_API_KEY}",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Accept": "image/*",
                },
            )
            with urllib.request.urlopen(http_req, timeout=30) as resp:
                img_data = resp.read()

            if not img_data or len(img_data) < 1000:
                return False, "empty or invalid image response"
        except Exception as exc:
            return False, str(exc)

        # Step 2: Animate with Ken Burns zoom
        img_path = output_dir / f"stability_{uuid.uuid4().hex[:8]}.png"
        out_path = output_dir / f"stability_{uuid.uuid4().hex[:8]}.mp4"
        img_path.write_bytes(img_data)

        dur = req.duration
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img_path),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", (
                f"zoompan=z='1+0.03*in/{dur}/24'"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={dur * 24}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps=24"
            ),
            "-t", str(dur),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=False)
            img_path.unlink(missing_ok=True)
        except Exception as exc:
            img_path.unlink(missing_ok=True)
            return False, str(exc)

        if out_path.exists():
            return True, str(out_path)
        return False, "ffmpeg ken-burns animation failed"

    def get_status(self, external_id: str) -> Tuple[str, float]:
        if external_id and Path(external_id).exists():
            return "completed", 1.0
        return "failed", 0.0

    def get_result(self, external_id: str, output_dir: Path) -> Optional[Path]:
        p = Path(external_id)
        return p if p.exists() else None
