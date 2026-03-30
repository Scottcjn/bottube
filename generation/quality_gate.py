"""
generation/quality_gate.py - Quality check before auto-publish
================================================================
Prevents low-quality or fallback output from auto-publishing.
Every completed generation job passes through the gate before
the publish step. Failed gates require manual user approval.

Checks:
  1. File exists and has minimum size (not empty/corrupt)
  2. Resolution above minimum threshold
  3. Has actual motion (not a static frame)
  4. No blank/black frames dominating
  5. Fallback output (ffmpeg titlecard) requires approval, not auto-publish
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("generation.quality_gate")

MIN_FILE_KB = 10
MIN_DURATION = 1.0
MIN_RESOLUTION = 240


@dataclass
class QualityGateResult:
    passed: bool
    score: int          # 0-100
    reason: str = ""
    requires_approval: bool = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": self.score,
            "reason": self.reason,
            "requires_approval": self.requires_approval,
        }


def check_quality(
    video_path: str,
    provider: str,
    provider_meta: Optional[dict] = None,
) -> QualityGateResult:
    """Run quality checks on generated video.  Returns gate result."""
    meta = provider_meta or {}
    path = Path(video_path)

    # Gate 1: File exists and is non-trivial
    if not path.exists():
        return QualityGateResult(False, 0, "Output file missing")

    size_kb = path.stat().st_size / 1024
    if size_kb < MIN_FILE_KB:
        return QualityGateResult(False, 5, f"File too small ({size_kb:.0f}KB)")

    # Gate 2: Fallback provider always requires approval (never auto-publish)
    if meta.get("is_fallback") or meta.get("requires_approval"):
        return QualityGateResult(
            False, 30,
            f"Fallback provider '{provider}' -- requires manual approval",
            requires_approval=True,
        )
    if provider == "ffmpeg_titlecard":
        return QualityGateResult(
            False, 25,
            "Title card fallback -- no real video generation occurred",
            requires_approval=True,
        )

    # Gate 3: Check video has actual frames (not blank/corrupt)
    score = 60  # base score for having a real video
    duration = _probe_duration(path)
    if duration is not None:
        if duration < MIN_DURATION:
            return QualityGateResult(
                False, 20, f"Video too short ({duration:.1f}s)"
            )
        if duration >= 2.0:
            score += 10
        if duration >= 4.0:
            score += 10

    # Gate 4: Resolution check
    width, height = _probe_resolution(path)
    if width and height:
        if min(width, height) < MIN_RESOLUTION:
            return QualityGateResult(
                False, 15,
                f"Resolution too low ({width}x{height})",
            )
        if width >= 512 and height >= 512:
            score += 10
        if width >= 720 and height >= 720:
            score += 10
    else:
        score -= 10  # can't determine resolution

    # Gate 5: Black/blank frame detection
    black_ratio = _detect_black_ratio(path)
    if black_ratio is not None and black_ratio > 0.80:
        return QualityGateResult(
            False, 10,
            f"Mostly black frames ({black_ratio:.0%})",
        )

    # Gate 6: Motion detection (optional, soft penalty)
    motion = _detect_motion(path)
    if motion is not None:
        if motion < 0.5:
            # Ken Burns providers (gemini, stability) have low motion by design
            if provider not in ("gemini", "stability"):
                score -= 15
        elif motion > 3.0:
            score += 5

    # Gate 7: Provider quality tier bonus
    quality_tier = meta.get("quality_tier", 3)
    score = min(100, score + quality_tier * 2)

    passed = score >= 50
    dur_str = f"{duration:.1f}s" if duration else "?"
    reason = f"Score {score}/100 (provider={provider}, dur={dur_str})"
    return QualityGateResult(passed, score, reason)


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------

def _probe_duration(path: Path) -> Optional[float]:
    """Get video duration via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def _probe_resolution(path: Path) -> Tuple[Optional[int], Optional[int]]:
    """Get video width x height via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                str(path),
            ],
            capture_output=True, text=True, timeout=10, check=False,
        )
        parts = result.stdout.strip().split("x")
        return int(parts[0]), int(parts[1])
    except Exception:
        return None, None


def _detect_black_ratio(path: Path) -> Optional[float]:
    """Return ratio (0.0-1.0) of video that is black."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", str(path),
                "-vf", "blackdetect=d=0.04:pix_th=0.10",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=30, check=False,
        )
        stderr = result.stderr
        total_black = 0.0
        for line in stderr.split("\n"):
            if "black_duration:" in line:
                try:
                    dur_str = line.split("black_duration:")[1].strip().split()[0]
                    total_black += float(dur_str)
                except (IndexError, ValueError):
                    pass

        total_dur = _probe_duration(path) or 1.0
        if total_dur <= 0:
            total_dur = 1.0
        return min(1.0, total_black / total_dur)
    except Exception:
        return None


def _detect_motion(path: Path) -> Optional[float]:
    """Estimate motion level.  Higher = more motion."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", str(path),
                "-vf", "tblend=all_mode=difference,blackframe=amount=0:threshold=10",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=30, check=False,
        )
        blackframe_count = result.stderr.count("blackframe:")
        if blackframe_count == 0:
            return 10.0
        return max(0.0, 10.0 - blackframe_count * 0.5)
    except Exception:
        return None
