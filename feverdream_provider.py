"""
feverdream_provider.py — BoTTube video provider for retro-CGI shorts.

Wraps the bottube-feverdream pipeline (AI -> POV-Ray scene -> rendered mp4) as a
standard BoTTube video provider. Unlike the cloud diffusion backends this one is
LOCAL and FREE (no API key), deterministic, and far cheaper per second of video,
so it registers as an always-available backend.

Provider contract (matches video_gen_blueprint backends):
    _try_feverdream(prompt: str, duration: int, output_path: Path) -> bool
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Where the bottube-feverdream checkout lives. Override with RETRO_CGI_DIR.
RETRO_CGI_DIR = Path(os.environ.get("RETRO_CGI_DIR", "/home/scott/retro-cgi"))
MAKE_VIDEO = RETRO_CGI_DIR / "make_video.sh"

# Render resolution/fps for BoTTube shorts. Keep modest so CPU render stays fast.
FD_FPS = int(os.environ.get("FD_FPS", "18"))
FD_WIDTH = int(os.environ.get("FD_WIDTH", "1280"))
FD_HEIGHT = int(os.environ.get("FD_HEIGHT", "720"))
# Safety cap on render wall-time, scaled by clip length (CPU raytracer).
FD_SECS_PER_FRAME_BUDGET = float(os.environ.get("FD_SPF_BUDGET", "8"))


def feverdream_available() -> bool:
    """True if the pipeline is present and runnable on this host."""
    return MAKE_VIDEO.exists() and os.access(MAKE_VIDEO, os.X_OK)


def _try_feverdream(prompt: str, duration: int, output_path: Path) -> bool:
    """Generate a retro-CGI clip for `prompt` into `output_path`. Returns success."""
    if not feverdream_available():
        return False

    secs = max(2, min(int(duration or 6), 15))   # clamp to a sane short length
    timeout = int(secs * FD_FPS * FD_SECS_PER_FRAME_BUDGET) + 120

    cmd = [
        str(MAKE_VIDEO),
        prompt,
        str(output_path),
        str(secs),
        str(FD_FPS),
        str(FD_WIDTH),
        str(FD_HEIGHT),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       cwd=str(RETRO_CGI_DIR))
    except Exception:
        return False
    # success = a non-trivial mp4 landed at the target path
    return output_path.exists() and output_path.stat().st_size > 50000


def register(registry) -> bool:
    """Register the feverdream provider on a ProviderRegistry. Returns True if added.

    No API key required, so it is always available where the pipeline is present.
    """
    if not feverdream_available():
        return False
    registry.register("feverdream", _try_feverdream)
    return True
