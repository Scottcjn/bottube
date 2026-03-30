"""
HuggingFace Inference API provider
====================================
Uses the free-tier text-to-video model (ali-vilab/text-to-video-ms-1.7b).
Synchronous: sends prompt, receives raw video bytes or retries on cold-start.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Optional, Tuple

from generation.models import GenerationMode, GenerationRequest
from generation.provider import GenerationProvider, ProviderCapabilities

log = logging.getLogger("generation.providers.huggingface")

HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "")
HF_VIDEO_MODEL = os.environ.get("HF_VIDEO_MODEL", "ali-vilab/text-to-video-ms-1.7b")
HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_VIDEO_MODEL}"

VIDEO_WIDTH = 720
VIDEO_HEIGHT = 720


class HuggingFaceProvider(GenerationProvider):

    def get_name(self) -> str:
        return "huggingface"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="huggingface",
            modes=[GenerationMode.text_to_video],
            max_duration=8,
            max_resolution=(512, 512),
            supports_audio=False,
            supports_captions=False,
            estimated_latency_s=90.0,
            quality_tier=3,
            cost_tier=1,
            requires_api_key=True,
            available=bool(HF_API_TOKEN),
        )

    def validate_input(self, req: GenerationRequest) -> Tuple[bool, str]:
        if not req.prompt:
            return False, "prompt is required"
        if not HF_API_TOKEN:
            return False, "HF_API_TOKEN not configured"
        if req.mode != GenerationMode.text_to_video:
            return False, "huggingface only supports text_to_video"
        return True, ""

    def submit(self, req: GenerationRequest, output_dir: Path) -> Tuple[bool, str]:
        """Synchronous call -- blocks until video bytes arrive."""
        num_frames = min(req.duration * 8, 64)
        payload = json.dumps({
            "inputs": req.prompt,
            "parameters": {"num_frames": num_frames},
        }).encode()

        for attempt in range(2):
            try:
                http_req = urllib.request.Request(
                    HF_API_URL,
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {HF_API_TOKEN}",
                        "Content-Type": "application/json",
                        "Accept": "video/mp4,application/json",
                    },
                )
                timeout = 180 if attempt > 0 else 120
                with urllib.request.urlopen(http_req, timeout=timeout) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    raw = resp.read()

                if "video" in content_type or "octet-stream" in content_type:
                    out_path = self._reencode(raw, req.duration, output_dir)
                    if out_path:
                        return True, str(out_path)
                    return False, "re-encode failed"

                # JSON response -- probably model loading
                body = json.loads(raw)
                err = body.get("error", "")
                if "loading" in err and attempt == 0:
                    log.info("HF model cold-starting, waiting 30s...")
                    time.sleep(30)
                    continue
                return False, err or "unexpected json response"

            except Exception as exc:
                if attempt == 0:
                    time.sleep(10)
                    continue
                return False, str(exc)

        return False, "all attempts exhausted"

    def get_status(self, external_id: str) -> Tuple[str, float]:
        # Synchronous provider -- result is the file path
        if external_id and Path(external_id).exists():
            return "completed", 1.0
        return "failed", 0.0

    def get_result(self, external_id: str, output_dir: Path) -> Optional[Path]:
        p = Path(external_id)
        return p if p.exists() else None

    # ------------------------------------------------------------------
    @staticmethod
    def _reencode(raw_bytes: bytes, duration: int, output_dir: Path) -> Optional[Path]:
        raw_path = output_dir / f"hf_raw_{uuid.uuid4().hex[:8]}.mp4"
        out_path = output_dir / f"hf_{uuid.uuid4().hex[:8]}.mp4"
        raw_path.write_bytes(raw_bytes)
        try:
            cmd = [
                "ffmpeg", "-y", "-i", str(raw_path),
                "-vf", (
                    f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
                    f":force_original_aspect_ratio=decrease,"
                    f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x1a1a2e"
                ),
                "-t", str(duration),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest",
                str(out_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=60, check=False)
            raw_path.unlink(missing_ok=True)
            return out_path if out_path.exists() else None
        except Exception:
            raw_path.unlink(missing_ok=True)
            return None
