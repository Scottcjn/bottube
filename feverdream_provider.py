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
import signal
import subprocess
from pathlib import Path

# Where the bottube-feverdream checkout lives. Override with RETRO_CGI_DIR.
RETRO_CGI_DIR = Path(os.environ.get("RETRO_CGI_DIR", "/home/scott/retro-cgi"))
MAKE_VIDEO = RETRO_CGI_DIR / "make_video.sh"

# Render resolution/fps for BoTTube shorts. Keep modest so CPU render stays fast.
FD_FPS = int(os.environ.get("FD_FPS", "18"))
FD_WIDTH = int(os.environ.get("FD_WIDTH", "1280"))
FD_HEIGHT = int(os.environ.get("FD_HEIGHT", "720"))
# One shared max clip length (kept in sync with the addon's FEVERDREAM_MAX_SECS).
FD_MAX_SECS = int(os.environ.get("FEVERDREAM_MAX_SECS", "8"))
# Safety cap on render wall-time, scaled by clip length (CPU raytracer).
FD_SECS_PER_FRAME_BUDGET = float(os.environ.get("FD_SPF_BUDGET", "8"))


def feverdream_available() -> bool:
    """True if the pipeline is present and runnable on this host."""
    return MAKE_VIDEO.exists() and os.access(MAKE_VIDEO, os.X_OK)


def _has_valid_mp4(path: Path) -> bool:
    """Validate the file is a real, non-trivial mp4 via ffprobe (not a stub)."""
    if not path.exists() or path.stat().st_size <= 50000:
        return False
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30)
        return r.returncode == 0 and "video" in r.stdout
    except Exception:
        return False


def _try_feverdream(prompt: str, duration: int, output_path: Path) -> bool:
    """Generate a retro-CGI clip for `prompt` into `output_path`. Returns success."""
    if not feverdream_available():
        return False

    secs = max(2, min(int(duration or 6), FD_MAX_SECS))
    timeout = int(secs * FD_FPS * FD_SECS_PER_FRAME_BUDGET) + 120

    # never accept a stale file from a previous (failed) render
    output_path.unlink(missing_ok=True)

    cmd = [str(MAKE_VIDEO), prompt, str(output_path),
           str(secs), str(FD_FPS), str(FD_WIDTH), str(FD_HEIGHT)]
    # run in its own process group so a timeout kills the whole render tree
    try:
        proc = subprocess.Popen(cmd, cwd=str(RETRO_CGI_DIR),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()
            return False
    except Exception:
        return False
    # success = exit 0 AND a validated mp4 landed at the target path
    return rc == 0 and _has_valid_mp4(output_path)


def register(registry) -> bool:
    """Register the feverdream provider on a ProviderRegistry. Returns True if added.

    No API key required, so it is always available where the pipeline is present.
    """
    if not feverdream_available():
        return False
    registry.register("feverdream", _try_feverdream)
    return True
