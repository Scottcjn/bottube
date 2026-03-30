"""
Google Gemini provider
=======================
Uses Gemini 2.0 Flash to generate an image, then animates it with
a Ken Burns zoom effect via ffmpeg.  Free tier.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Tuple

from generation.models import GenerationMode, GenerationRequest
from generation.provider import GenerationProvider, ProviderCapabilities

log = logging.getLogger("generation.providers.gemini")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-2.0-flash:generateContent"
)
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 720


class GeminiProvider(GenerationProvider):

    def get_name(self) -> str:
        return "gemini"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="gemini",
            modes=[
                GenerationMode.text_to_video,
                GenerationMode.text_to_image_sequence,
            ],
            max_duration=15,
            max_resolution=(1280, 720),
            supports_audio=False,
            supports_captions=False,
            estimated_latency_s=20.0,
            quality_tier=3,
            cost_tier=1,
            requires_api_key=True,
            available=bool(GEMINI_API_KEY),
            styles=["digital_art", "photorealistic", "illustration"],
        )

    def validate_input(self, req: GenerationRequest) -> Tuple[bool, str]:
        if not req.prompt:
            return False, "prompt is required"
        if not GEMINI_API_KEY:
            return False, "GEMINI_API_KEY not configured"
        return True, ""

    def submit(self, req: GenerationRequest, output_dir: Path) -> Tuple[bool, str]:
        import urllib.request

        payload = json.dumps({
            "contents": [{
                "parts": [{
                    "text": (
                        f"Generate a vivid, cinematic image for this scene: {req.prompt}. "
                        "Style: digital art, 16:9 composition, vibrant colors."
                    )
                }]
            }],
            "generationConfig": {
                "responseModalities": ["image", "text"],
                "imageSizeOptions": {"width": 1280, "height": 720},
            },
        }).encode()

        http_req = urllib.request.Request(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(http_req, timeout=30) as resp:
                result = json.loads(resp.read())
        except Exception as exc:
            return False, str(exc)

        # Extract image
        candidates = result.get("candidates", [])
        if not candidates:
            return False, "no candidates returned"

        parts = candidates[0].get("content", {}).get("parts", [])
        img_data = None
        for part in parts:
            if "inlineData" in part:
                img_data = base64.b64decode(part["inlineData"]["data"])
                break

        if not img_data:
            return False, "no image in response"

        # Save image and animate with Ken Burns
        img_path = output_dir / f"gemini_{uuid.uuid4().hex[:8]}.png"
        out_path = output_dir / f"gemini_{uuid.uuid4().hex[:8]}.mp4"
        img_path.write_bytes(img_data)

        dur = req.duration
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img_path),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", (
                f"scale=1440:1440,"
                f"zoompan=z='1+0.04*in/{dur}/24'"
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
