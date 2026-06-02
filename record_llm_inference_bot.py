#!/usr/bin/env python3
"""
Record LLM Inference on Unusual Hardware — BoTTube Upload Bot (Bounty #645)

Uploads a pre-recorded video of an LLM running on unusual/vintage/exotic hardware
to BoTTube, with appropriate tags and provenance description.

Usage:
    # Upload a video with description
    python3 record_llm_inference_bot.py --video /path/to/demo.mp4 --title "Llama on PowerPC" --description "Shows llama.cpp generating text on a PowerMac G5" --hardware "PowerMac G5"

    # Dry-run (validate file without uploading)
    python3 record_llm_inference_bot.py --video demo.mp4 --dry-run

Environment:
    BOTTUBE_API_KEY    (required for upload)
    BOTTUBE_URL        (optional, default https://bottube.ai)
"""

import argparse
import logging
import os
import sys
import subprocess
import tempfile
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BOTTUBE_URL = os.environ.get("BOTTUBE_URL", "https://bottube.ai").rstrip("/")
BOTTUBE_API_KEY = os.environ.get("BOTTUBE_API_KEY")
VERIFY_SSL = os.environ.get("BOTTUBE_VERIFY_SSL", "1").lower() not in {"0", "false", "no"}
MAX_DURATION = 8          # seconds
MAX_WIDTH = 720
MAX_HEIGHT = 720

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("unusual_hardware")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Upload a video of LLM inference on unusual hardware to BoTTube (Bounty #645)."
    )
    parser.add_argument(
        "--video",
        required=True,
        help="Path to the recorded video file (mp4, webm, etc.)",
    )
    parser.add_argument(
        "--title",
        default="Unusual Hardware LLM Inference",
        help="Title for the video",
    )
    parser.add_argument(
        "--description",
        default="",
        help="Description of the hardware and what is shown",
    )
    parser.add_argument(
        "--hardware",
        default="",
        help="Hardware name (e.g., Raspberry Pi 5, POWER8)",
    )
    parser.add_argument(
        "--tags",
        default="unusual-hardware,llm-inference,bounty-645",
        help="Comma-separated tags (default: unusual-hardware,llm-inference,bounty-645)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the video file but do not upload",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="BoTTube API key (overrides BOTTUBE_API_KEY env)",
    )
    return parser.parse_args()


def prepare_video(input_path: str, output_dir: str) -> str:
    """Resize and compress video to meet BoTTube constraints."""
    output_path = os.path.join(output_dir, "upload_ready.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-t", str(MAX_DURATION),
        "-vf", (
            f"scale='min({MAX_WIDTH},iw)':'min({MAX_HEIGHT},ih)':"
            f"force_original_aspect_ratio=decrease,"
            f"pad={MAX_WIDTH}:{MAX_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black"
        ),
        "-c:v", "libx264",
        "-crf", "28",
        "-preset", "medium",
        "-maxrate", "900k",
        "-bufsize", "1800k",
        "-pix_fmt", "yuv420p",
        "-an",
        "-movflags", "+faststart",
        output_path,
    ]
    log.info("Transcoding video...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("ffmpeg failed:\n%s", result.stderr)
        raise RuntimeError("Video transcoding failed")
    log.info("Video prepared: %s", output_path)
    return output_path


def upload_video(video_path: str, title: str, description: str, tags: str, api_key: str):
    """Upload video to BoTTube agent API."""
    url = f"{BOTTUBE_URL}/api/upload"
    headers = {"X-API-Key": api_key}
    files = {"video": open(video_path, "rb")}
    data = {
        "title": title,
        "description": description,
        "tags": tags,
    }
    log.info("Uploading to %s ...", url)
    resp = requests.post(
        url,
        headers=headers,
        files=files,
        data=data,
        verify=VERIFY_SSL,
        timeout=120,
    )
    if resp.status_code in (200, 201):
        result = resp.json()
        log.info("Upload successful! Video ID: %s", result.get("video_id", "unknown"))
        return result
    else:
        log.error("Upload failed (HTTP %d): %s", resp.status_code, resp.text)
        raise RuntimeError(f"Upload failed: {resp.text}")


def main():
    args = parse_args()

    # Resolve API key
    api_key = args.api_key or BOTTUBE_API_KEY
    if not api_key:
        log.error("API key required: set BOTTUBE_API_KEY or pass --api-key")
        sys.exit(1)

    # Check input file
    video_path = Path(args.video)
    if not video_path.exists():
        log.error("Video file not found: %s", video_path)
        sys.exit(1)

    # Build description with hardware info
    description = args.description
    if args.hardware and args.hardware not in description:
        description = f"Hardware: {args.hardware}\n\n{description}"

    if args.dry_run:
        log.info("DRY RUN: Video '%s' would be uploaded with:", args.video)
        log.info("  Title: %s", args.title)
        log.info("  Description: %s", description)
        log.info("  Tags: %s", args.tags)
        log.info("  API Key: %s...", api_key[:8] if len(api_key) > 8 else "***")
        return

    # Prepare video (transcode)
    with tempfile.TemporaryDirectory(prefix="bottube_upload_") as tmpdir:
        try:
            processed = prepare_video(str(video_path), tmpdir)
            upload_video(processed, args.title, description, args.tags, api_key)
        except Exception as e:
            log.error("Failed: %s", e, exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
