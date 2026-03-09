#!/usr/bin/env python3
"""
BoTTube Vision Screening Module
3-tier pipeline for detecting spam/placeholder video uploads.

Tier 1: Local heuristics (instant, runs on VPS)
Tier 2: MiniCPM-V4.5 vision model via proxy (.131 -> POWER8 Ollama)
Tier 3: Future Hailo-8 YOLO on .133 (stub)
"""

import base64
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("vision_screener")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Vision proxy on .131 forwards to POWER8 Ollama (MiniCPM-V4.5)
VISION_PROXY_URL = os.environ.get(
    "VISION_PROXY_URL", "http://50.28.86.131:8097"
)
NAS_OLLAMA_URL = os.environ.get(
    "VISION_OLLAMA_URL", "http://100.75.100.89:11434"
)
VISION_MODEL = os.environ.get("VISION_MODEL", "openbmb/minicpm-v4.5:latest")
HAILO_URL = os.environ.get("HAILO_URL", "http://50.28.86.131:8097")

# Tier 1 thresholds
COLOR_VARIANCE_THRESHOLD = 15.0  # Pixels: if std-dev < this, nearly solid color
ENTROPY_THRESHOLD = 3.0          # Bits: real video frames have entropy > 5
SIMILARITY_THRESHOLD = 0.98      # SSIM: if all frames are >98% similar, it's frozen
MIN_EDGE_DENSITY = 0.02          # Fraction of edge pixels (real content > 2%)

# Tier 2 thresholds
VISION_QUALITY_THRESHOLD = 4     # Quality score 1-10 from vision model
VISION_TIMEOUT = 120             # Seconds to wait for vision API (POWER8 CPU inference)


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def extract_frames(video_path: str, count: int = 3) -> list:
    """Extract evenly-spaced frames from a video using ffmpeg.

    Returns list of paths to temporary PNG files.
    """
    frames = []
    try:
        # Get video duration
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", video_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        info = json.loads(probe.stdout)
        duration = float(info.get("format", {}).get("duration", 0))
        if duration <= 0:
            duration = 1.0

        # Calculate timestamps for evenly-spaced frames
        timestamps = []
        if count == 1:
            timestamps = [duration * 0.5]
        else:
            for i in range(count):
                t = (duration * i) / (count - 1) if count > 1 else 0
                # Clamp to avoid seeking past end
                timestamps.append(min(t, max(0, duration - 0.1)))

        tmpdir = tempfile.mkdtemp(prefix="bottube_screen_")
        for i, ts in enumerate(timestamps):
            out_path = os.path.join(tmpdir, f"frame_{i}.png")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", str(ts),
                    "-i", video_path,
                    "-frames:v", "1",
                    "-vf", "scale=320:-1",
                    out_path,
                ],
                capture_output=True, timeout=10,
            )
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                frames.append(out_path)

    except Exception as e:
        logger.warning("Frame extraction failed: %s", e)

    return frames


# ---------------------------------------------------------------------------
# Tier 1: Local heuristics (no external calls)
# ---------------------------------------------------------------------------

def _get_pixel_stats(frame_path: str) -> dict:
    """Use ffprobe to get basic pixel statistics from a frame."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "frame=width,height",
                "-show_entries", "frame_tags=lavfi.signalstats.YAVG,lavfi.signalstats.YMIN,lavfi.signalstats.YMAX",
                "-f", "lavfi",
                "-i", f"movie={frame_path},signalstats",
                "-of", "json",
            ],
            capture_output=True, text=True, timeout=10,
        )
        return json.loads(result.stdout)
    except Exception:
        return {}


def _frame_entropy(frame_path: str) -> float:
    """Compute Shannon entropy of a frame using ffmpeg entropy filter.

    Falls back to file-size heuristic if filter unavailable.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries",
                "frame_tags=lavfi.entropy.entropy.normal.Y",
                "-f", "lavfi",
                "-i", f"movie={frame_path},entropy",
                "-of", "csv=p=0",
            ],
            capture_output=True, text=True, timeout=10,
        )
        val = result.stdout.strip()
        if val:
            return float(val)
    except Exception:
        pass

    # Fallback: use file size as proxy (tiny PNG = low complexity)
    try:
        size = os.path.getsize(frame_path)
        # A 320px wide frame with real content is typically 15-80KB
        # Solid color / simple pattern is 1-5KB
        if size < 3000:
            return 1.0  # Very low entropy
        elif size < 8000:
            return 3.5
        else:
            return 6.0  # Probably real content
    except Exception:
        return 5.0  # Assume OK if we can't check


def _color_variance(frame_path: str) -> float:
    """Measure color variance across a frame.

    Uses ffmpeg to compute standard deviation of pixel values.
    Low variance = solid color or near-solid background.
    """
    try:
        # Use ffmpeg to compute mean and stdev of luminance
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries",
                "frame_tags=lavfi.signalstats.YAVG,lavfi.signalstats.YLOW,lavfi.signalstats.YHIGH",
                "-f", "lavfi",
                "-i", f"movie={frame_path},signalstats=stat=tout+vrep+brng",
                "-of", "csv=p=0",
            ],
            capture_output=True, text=True, timeout=10,
        )
        parts = result.stdout.strip().split(",")
        if len(parts) >= 3:
            yavg = float(parts[0])
            ylow = float(parts[1])
            yhigh = float(parts[2])
            return yhigh - ylow  # Range as variance proxy
    except Exception:
        pass

    # Fallback: file size proxy
    try:
        size = os.path.getsize(frame_path)
        return 5.0 if size < 3000 else 50.0
    except Exception:
        return 50.0


def _frames_similar(frame_paths: list) -> float:
    """Check if all frames are nearly identical (static/frozen video).

    Returns similarity score 0.0-1.0. Uses PSNR as proxy for SSIM.
    """
    if len(frame_paths) < 2:
        return 0.0

    try:
        # Compare first and last frame using ffmpeg PSNR
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", frame_paths[0],
                "-i", frame_paths[-1],
                "-lavfi", "psnr", "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=10,
        )
        # Parse PSNR from stderr
        import re
        for line in result.stderr.split("\n"):
            if "average:" in line.lower():
                m = re.search(r"average:(\d+\.?\d*)", line)
                if m:
                    psnr = float(m.group(1))
                    if psnr > 50:
                        return 0.99
                    elif psnr > 40:
                        return 0.95
                    elif psnr > 30:
                        return 0.8
                    else:
                        return 0.5
    except Exception:
        pass

    return 0.0


def tier1_heuristics(video_path: str, frames: list) -> dict:
    """Run local heuristic checks on extracted frames.

    Returns dict with:
        passed: bool
        flags: list of triggered flags
        details: dict of measurements
    """
    flags = []
    details = {}

    if not frames:
        return {"passed": False, "flags": ["no_frames_extracted"], "details": {}}

    # Check 1: Color variance (solid color detection)
    variances = []
    for fp in frames:
        v = _color_variance(fp)
        variances.append(v)
    avg_variance = sum(variances) / len(variances) if variances else 50.0
    details["color_variance"] = round(avg_variance, 2)
    if avg_variance < COLOR_VARIANCE_THRESHOLD:
        flags.append("solid_color")

    # Check 2: Entropy (low complexity detection)
    entropies = []
    for fp in frames:
        e = _frame_entropy(fp)
        entropies.append(e)
    avg_entropy = sum(entropies) / len(entropies) if entropies else 5.0
    details["entropy"] = round(avg_entropy, 2)
    if avg_entropy < ENTROPY_THRESHOLD:
        flags.append("low_entropy")

    # Check 3: Frame similarity (frozen video detection)
    if len(frames) >= 2:
        sim = _frames_similar(frames)
        details["frame_similarity"] = round(sim, 3)
        if sim > SIMILARITY_THRESHOLD:
            flags.append("frozen_video")

    # Overall verdict
    passed = len(flags) == 0
    details["tier"] = 1
    return {"passed": passed, "flags": flags, "details": details}


# ---------------------------------------------------------------------------
# Tier 2: MiniCPM-V4.5 via vision proxy (.131 -> POWER8)
# ---------------------------------------------------------------------------

def _encode_frame_base64(frame_path: str) -> str:
    """Read a frame file and return base64-encoded string."""
    with open(frame_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _tier2_direct_ollama(img_b64: str, proxy_error: str = "") -> dict:
    """Fallback: call Ollama directly if proxy is unreachable."""
    prompt = (
        "Analyze this video frame. Answer these questions:\n"
        "1. DESCRIPTION: What does this frame show? (1-2 sentences)\n"
        "2. IS_SPAM: Is this spam content? Answer YES or NO.\n"
        "3. QUALITY: Rate visual quality 1-10.\n\n"
        "Format: DESCRIPTION: ...\nIS_SPAM: YES/NO\nQUALITY: N"
    )

    try:
        import urllib.request
        payload = json.dumps({
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 200},
        }).encode()
        req = urllib.request.Request(
            f"{NAS_OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=VISION_TIMEOUT) as resp:
            data = json.loads(resp.read())
            response_text = data.get("response", "")
    except Exception as e2:
        logger.warning("Tier 2 direct Ollama also failed: %s", e2)
        return {
            "passed": True,
            "quality_score": 5,
            "description": f"Vision unavailable (proxy: {proxy_error}, direct: {e2})",
            "is_spam": False,
            "details": {"tier": 2, "error": str(e2), "proxy_error": proxy_error, "fallback": True},
        }

    quality_score = 5
    is_spam = False
    description = response_text.strip()

    for line in response_text.split("\n"):
        line_upper = line.strip().upper()
        if line_upper.startswith("QUALITY:"):
            try:
                score_str = line.split(":", 1)[1].strip().split("/")[0].split()[0]
                quality_score = max(1, min(10, int(float(score_str))))
            except (ValueError, IndexError):
                pass
        elif line_upper.startswith("IS_SPAM:"):
            val = line.split(":", 1)[1].strip().upper()
            is_spam = val.startswith("YES")
        elif line_upper.startswith("DESCRIPTION:"):
            description = line.split(":", 1)[1].strip()

    passed = quality_score >= VISION_QUALITY_THRESHOLD and not is_spam
    return {
        "passed": passed,
        "quality_score": quality_score,
        "description": description,
        "is_spam": is_spam,
        "details": {
            "tier": 2,
            "model": VISION_MODEL,
            "via": "direct_ollama",
            "raw_response": response_text[:500],
        },
    }


def tier2_vision(frames: list) -> dict:
    """Send a representative frame to vision proxy for quality assessment.

    Uses the vision proxy on .131 which forwards to POWER8 Ollama.
    Falls back to direct Ollama call if proxy unreachable.

    Returns dict with:
        passed: bool
        quality_score: int (1-10)
        description: str
        is_spam: bool
        details: dict
    """
    if not frames:
        return {
            "passed": False,
            "quality_score": 0,
            "description": "No frames available",
            "is_spam": True,
            "details": {"tier": 2, "error": "no_frames"},
        }

    # Use the middle frame (best representative)
    mid = len(frames) // 2
    frame_path = frames[mid]

    try:
        img_b64 = _encode_frame_base64(frame_path)
    except Exception as e:
        return {
            "passed": False,
            "quality_score": 0,
            "description": f"Frame encoding failed: {e}",
            "is_spam": True,
            "details": {"tier": 2, "error": str(e)},
        }

    # Try vision proxy first (chain: .153 -> .131:8097 -> POWER8:11434)
    try:
        import urllib.request
        payload = json.dumps({
            "image_base64": img_b64,
        }).encode()
        req = urllib.request.Request(
            f"{VISION_PROXY_URL}/analyze",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=VISION_TIMEOUT) as resp:
            result = json.loads(resp.read())

        quality_score = result.get("quality_score", 5)
        is_spam = result.get("is_spam", False)
        description = result.get("description", "")
        passed = result.get("passed", True)

        return {
            "passed": passed,
            "quality_score": quality_score,
            "description": description,
            "is_spam": is_spam,
            "details": {
                "tier": 2,
                "model": result.get("model", VISION_MODEL),
                "via": "proxy",
                "raw_response": result.get("raw_response", "")[:500],
            },
        }
    except Exception as e:
        logger.warning("Tier 2 vision proxy failed: %s", e)
        # Fall back to direct Ollama call
        return _tier2_direct_ollama(img_b64, str(e))


# ---------------------------------------------------------------------------
# Tier 3: Hailo-8 YOLO (stub for future)
# ---------------------------------------------------------------------------

def tier3_hailo(frames: list) -> dict:
    """Send frames to detection service for YOLO object detection.

    Uses detection service at HAILO_URL.
    Falls back to passing if service is unreachable.
    """
    if not frames:
        return {"passed": True, "objects_detected": 0, "details": {"tier": 3, "error": "no_frames"}}

    total_objects = 0
    spam_scores = []
    frame_results = []

    for fp in frames[:2]:  # Check up to 2 frames
        try:
            with open(fp, "rb") as f:
                img_data = f.read()

            import urllib.request
            req = urllib.request.Request(
                f"{HAILO_URL}/detect-spam",
                data=img_data,
                headers={"Content-Type": "application/octet-stream"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())

            detection = result.get("detection", {})
            spam = result.get("spam_analysis", {})

            total_objects += detection.get("count", 0)
            spam_scores.append(spam.get("spam_score", 0.0))
            frame_results.append({
                "objects": detection.get("count", 0),
                "inference_ms": detection.get("inference_ms", 0),
                "spam_score": spam.get("spam_score", 0),
                "reasons": spam.get("reasons", []),
            })

        except Exception as e:
            logger.debug("Tier 3 detection failed for frame: %s", e)
            return {"passed": True, "objects_detected": -1,
                    "details": {"tier": 3, "error": str(e), "fallback": True}}

    avg_spam = sum(spam_scores) / len(spam_scores) if spam_scores else 0.0
    passed = avg_spam < 0.6

    return {
        "passed": passed,
        "objects_detected": total_objects,
        "details": {
            "tier": 3,
            "avg_spam_score": round(avg_spam, 3),
            "frames_checked": len(frame_results),
            "frame_results": frame_results,
        },
    }


# ---------------------------------------------------------------------------
# Main screening pipeline
# ---------------------------------------------------------------------------

def screen_video(video_path: str, run_tier2: bool = True) -> dict:
    """Run the full screening pipeline on a video file.

    Args:
        video_path: Path to the video file on disk
        run_tier2: Whether to call the vision model (set False if unreachable)

    Returns dict with:
        status: "passed" | "failed" | "manual_review"
        tier_reached: int (1, 2, or 3)
        tier1: dict of tier 1 results
        tier2: dict of tier 2 results (if run)
        tier3: dict of tier 3 results (if run)
        summary: str human-readable summary
    """
    result = {
        "status": "passed",
        "tier_reached": 1,
        "tier1": {},
        "tier2": {},
        "tier3": {},
        "summary": "",
    }

    # Extract frames
    frames = extract_frames(video_path, count=3)
    if not frames:
        result["status"] = "failed"
        result["summary"] = "Could not extract any frames from video"
        result["tier1"] = {"passed": False, "flags": ["extraction_failed"], "details": {}}
        return result

    try:
        # Tier 1: Local heuristics
        t1 = tier1_heuristics(video_path, frames)
        result["tier1"] = t1

        if not t1["passed"]:
            # Tier 1 flagged -- escalate to Tier 2 if available
            if run_tier2:
                result["tier_reached"] = 2
                t2 = tier2_vision(frames)
                result["tier2"] = t2

                if not t2["passed"]:
                    result["status"] = "failed"
                    result["summary"] = (
                        f"Spam detected: {', '.join(t1['flags'])}. "
                        f"Vision confirms: quality={t2['quality_score']}/10, "
                        f"spam={t2['is_spam']}"
                    )
                else:
                    # Tier 1 flagged but Tier 2 says OK -- manual review
                    result["status"] = "manual_review"
                    result["summary"] = (
                        f"Heuristic flags: {', '.join(t1['flags'])}, "
                        f"but vision model says quality={t2['quality_score']}/10. "
                        f"Allowing with review flag."
                    )
            else:
                # No Tier 2 available -- fail on heuristics alone
                result["status"] = "failed"
                result["summary"] = f"Spam detected by heuristics: {', '.join(t1['flags'])}"
        else:
            # Tier 1 passed -- run Tier 3 Hailo YOLO for extra object detection
            try:
                t3 = tier3_hailo(frames)
                result["tier3"] = t3
                result["tier_reached"] = 3
                if not t3['passed']:
                    # Hailo says spam but heuristics passed -- flag for review
                    result["status"] = "manual_review"
                    spam_sc = t3.get("details", {}).get("avg_spam_score", "?")
                    result["summary"] = "Heuristics passed but Hailo flagged spam_score=" + str(spam_sc)
                elif t3.get('objects_detected', 0) == 0:
                    # No objects detected -- suspicious but not blocking
                    result["summary"] = "Passed heuristics, no objects detected by YOLO"
                else:
                    obj_ct = t3.get("objects_detected", 0)
                    result["summary"] = "Passed all checks (" + str(obj_ct) + " objects detected)"
            except Exception as e:
                logger.debug("Tier 3 skipped: %s", e)
                result["summary"] = "Passed heuristic checks (Tier 3 unavailable)"

    finally:
        # Clean up temporary frame files
        for fp in frames:
            try:
                os.unlink(fp)
            except OSError:
                pass
        # Try to remove temp directory
        if frames:
            try:
                os.rmdir(os.path.dirname(frames[0]))
            except OSError:
                pass

    return result
