"""
FFmpeg title-card fallback provider
=====================================
Always-works fallback: renders the prompt as styled text over a
gradient background with the bottube.ai watermark.

IMPORTANT: Output from this provider should NOT auto-publish.
The quality gate flags it as "fallback_titlecard" requiring approval.
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import textwrap
import uuid
from pathlib import Path
from typing import Optional, Tuple

from generation.models import GenerationMode, GenerationRequest
from generation.provider import GenerationProvider, ProviderCapabilities

log = logging.getLogger("generation.providers.ffmpeg_titlecard")

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")


class FFmpegTitleCardProvider(GenerationProvider):
    """Local ffmpeg text-on-gradient fallback. Always available."""

    def get_name(self) -> str:
        return "ffmpeg_titlecard"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="ffmpeg_titlecard",
            modes=[
                GenerationMode.text_to_video,
                GenerationMode.text_to_image_sequence,
                GenerationMode.remix,
            ],
            max_duration=30,
            max_resolution=(1080, 1080),
            supports_audio=False,
            supports_captions=False,
            estimated_latency_s=5.0,
            quality_tier=1,
            cost_tier=1,
            requires_api_key=False,
            available=True,
        )

    def validate_input(self, req: GenerationRequest) -> Tuple[bool, str]:
        if not req.prompt:
            return False, "Prompt required"
        return True, "ok"

    def submit(self, req: GenerationRequest, output_dir: Path) -> Tuple[bool, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"titlecard_{uuid.uuid4().hex[:8]}.mp4"

        lines = textwrap.wrap(req.prompt, width=35)
        display_text = "\\n".join(lines[:8])
        safe_text = display_text.replace("'", "'\\''").replace(":", "\\:")

        duration = min(req.duration, 30)
        ar = req.aspect_ratio or "1:1"
        w, h = {"16:9": (1280, 720), "9:16": (720, 1280)}.get(ar, (720, 720))

        cmd = (
            f'{FFMPEG} -y -f lavfi -i '
            f'"color=c=#1a0a2e:size={w}x{h}:duration={duration}:rate=24" '
            f'-vf "'
            f"drawtext=text='{safe_text}'"
            f":fontcolor=white:fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2"
            f":font=monospace:line_spacing=8,"
            f"drawtext=text='bottube.ai'"
            f":fontcolor=#ffffff40:fontsize=16:x=w-text_w-20:y=h-30"
            f'" -c:v libx264 -preset ultrafast -pix_fmt yuv420p '
            f'{shlex.quote(str(out_path))}'
        )

        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                return False, f"ffmpeg error: {result.stderr[:200]}"
            if not out_path.exists() or out_path.stat().st_size < 1000:
                return False, "ffmpeg produced empty output"
            return True, str(out_path)
        except subprocess.TimeoutExpired:
            return False, "ffmpeg timeout"
        except Exception as e:
            return False, f"ffmpeg error: {e}"

    def get_status(self, external_id: str) -> Tuple[str, float]:
        if external_id and Path(external_id).exists():
            return "completed", 1.0
        return "failed", 0.0

    def get_result(self, external_id: str, output_dir: Path) -> Optional[Path]:
        p = Path(external_id)
        return p if p.exists() else None
