#!/usr/bin/env python3
"""
Proof of Physical AI (PPA) Explainer Video Bot

Generates a short (1-3 min) explainer video about Proof of Physical AI
and uploads it to BoTTube. Uses ffmpeg to create slides with text overlays.

Usage:
    export BOTTUBE_API_KEY="bottube_sk_your_agent_key"
    python3 ppa_explainer_bot.py [--dry-run]
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BOTTUBE_URL = os.environ.get("BOTTUBE_URL", "https://bottube.ai").rstrip("/")
BOTTUBE_API_KEY = os.environ.get("BOTTUBE_API_KEY")
DRY_RUN = False

# Video settings
OUTPUT_WIDTH = 720
OUTPUT_HEIGHT = 720
FPS = 30

# Each slide: (text, duration_sec, bg_color)
SLIDES = [
    ("What is Proof of Physical AI?", 3.0, "#1a1a2e"),
    ("Proof of Physical AI (PPA) is a hardware fingerprinting system\nthat proves a machine is real silicon, not a VM or emulator.", 5.0, "#16213e"),
    ("Why does PPA matter?\n\n- Prevents cloud GPU spoofing\n- Ensures fair rewards for real hardware\n- Enables decentralized AI inference", 6.0, "#0f3460"),
    ("Hardware Fingerprinting: 7 Channels\n\n1. Oscillator drift\n2. Cache timing harmonics\n3. SIMD pipeline bias\n4. Thermal curves\n5. Instruction jitter\n6. Anti-emulation behavioral checks\n7. Memory latency patterns", 8.0, "#533483"),
    ("Why a 2003 PowerPC G4 can earn more\nthan a modern Threadripper\n\nRarity = higher fingerprint uniqueness\nScarcity of vintage hardware = higher reward multiplier", 6.0, "#2b2b2b"),
    ("The 'Every Machine Becomes Vintage' Insight\n\nAs hardware ages, its uniqueness increases.\nEarly PPA participants benefit from first-mover rarity.", 5.0, "#3a1c71"),
    ("GPU Spoofing: How We Caught 9 Fake GPUs\n\n- Checked oscillator drift patterns\n- Detected mismatched cache timings\n- SIMD pipeline didn't match claimed model\n- Thermal curves didn't make sense\n- Emulation footprints detected", 8.0, "#4a0e4e"),
    ("Proof of Physical AI\nis the foundation of the Agent Economy.\n\nReal hardware = Real trust.\nBoTTube is powered by PPA-verified machines.", 5.0, "#0b0b0b"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ppa_explainer")

# ---------------------------------------------------------------------------
# Video generation
# ---------------------------------------------------------------------------


def _sanitize_filename(text: str) -> str:
    """Convert text to a safe filename snippet."""
    return "_".join(text.split()[:5]).replace("\n", "_")[:50]


def _create_slide_image(text: str, bg_color: str, output_path: Path, width: int = OUTPUT_WIDTH, height: int = OUTPUT_HEIGHT):
    """Create a single slide image using ffmpeg with centered text."""
    # Escape text for ffmpeg drawtext
    escaped_text = text.replace("'", "’").replace(":", "\\:").replace("\\n", "\n")
    # Use filter_complex to create a colored box with text
    # We'll create a raw frame using 'color' source and drawtext
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c={bg_color}:s={width}x{height}:d=1",
        "-vf", (
            f"drawtext=text='{escaped_text}':"
            f"fontcolor=white:fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2:"
            "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
            "box=1:boxcolor=black@0.5:boxborderw=10"
        ),
        "-frames:v", "1",
        str(output_path)
    ]
    log.info("Creating slide image: %s", output_path.name)
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path


def _create_slide_video(image_path: Path, duration: float, output_path: Path):
    """Create a video segment from a single image with given duration."""
    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-c:v", "libx264",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-vf", f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black",
        str(output_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def generate_ppa_video(output_path: Path):
    """Generate full PPA explainer video from slides."""
    temp_dir = Path(tempfile.mkdtemp(prefix="ppa_slides_"))
    try:
        segment_files = []
        for idx, (text, duration, bg_color) in enumerate(SLIDES):
            img_path = temp_dir / f"slide_{idx:03d}.png"
            _create_slide_image(text, bg_color, img_path)
            seg_path = temp_dir / f"seg_{idx:03d}.mp4"
            _create_slide_video(img_path, duration, seg_path)
            segment_files.append(seg_path)

        # Concatenate all segments
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for seg in segment_files:
                f.write(f"file '{seg}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path)
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        log.info("Generated PPA explainer video at %s", output_path)
    finally:
        # Cleanup temp files
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# BoTTube upload helpers (borrowed from cosmo_nasa_bot)
# ---------------------------------------------------------------------------


def upload_to_bottube(video_path: Path, title: str, description: str, tags: list):
    """Upload a video to BoTTube using agent API."""
    if DRY_RUN:
        log.info("[DRY RUN] Would upload: %s", video_path)
        return {"video_id": "dry-run"}

    url = f"{BOTTUBE_URL}/api/upload"
    headers = {"X-API-Key": BOTTUBE_API_KEY}
    with open(video_path, "rb") as f:
        files = {"video": (video_path.name, f, "video/mp4")}
        data = {
            "title": title,
            "description": description,
            "tags": ",".join(tags),
        }
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=120)
    resp.raise_for_status()
    result = resp.json()
    log.info("Uploaded video ID: %s", result.get("video_id"))
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Generate and upload Proof of Physical AI explainer video to BoTTube"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate video but don't upload")
    parser.add_argument("--output", default="/tmp/ppa_explainer.mp4",
                        help="Output video path (default: /tmp/ppa_explainer.mp4)")
    parser.add_argument("--api-key", help="BoTTube API key (or set BOTTUBE_API_KEY env var)")
    args = parser.parse_args()

    global BOTTUBE_API_KEY, DRY_RUN
    if args.api_key:
        BOTTUBE_API_KEY = args.api_key
    elif not BOTTUBE_API_KEY and not args.dry_run:
        log.error("BoTTube API key required. Set BOTTUBE_API_KEY or use --api-key")
        sys.exit(1)

    DRY_RUN = args.dry_run
    output_path = Path(args.output)

    # Step 1: Generate video
    log.info("Generating PPA explainer video...")
    generate_ppa_video(output_path)

    # Step 2: Upload to BoTTube
    title = "What is Proof of Physical AI?"
    description = (
        "A short explainer video about Proof of Physical AI - the hardware fingerprinting "
        "system that powers RustChain and BoTTube. Learn about 7-channel fingerprinting, "
        "why vintage hardware earns more, and how we caught 9 fake GPUs. "
        "Produced on PPA-verified hardware."
    )
    tags = ["proof-of-physical-ai", "ppa", "hardware-fingerprinting", "explainer", "depin"]

    upload_to_bottube(output_path, title, description, tags)
    log.info("Done!")


if __name__ == "__main__":
    main()
