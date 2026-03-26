# SPDX-License-Identifier: MIT
"""
Best Frame Selector for BoTTube Thumbnails

Samples frames from a video at regular intervals, scores each frame based on
visual quality metrics (brightness, contrast, edge density), and saves the
highest-scoring frame as the default thumbnail.

Zero AI model dependencies -- pure ffmpeg + PIL/numpy.

CLI usage:
    python3 best_frame.py videos/xyz.mp4
    python3 best_frame.py videos/xyz.mp4 --output thumbnails/xyz.jpg
    python3 best_frame.py videos/xyz.mp4 --interval 1.0 --size 320x180
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except (ValueError, TypeError, subprocess.TimeoutExpired):
        return 0.0


def extract_frames(
    video_path: str,
    output_dir: str,
    interval: float = 0.5,
) -> List[Tuple[str, float]]:
    """Extract frames at regular intervals using ffmpeg.

    Returns list of (frame_path, timestamp) tuples.
    """
    duration = get_video_duration(video_path)
    if duration <= 0:
        return []

    frames: List[Tuple[str, float]] = []
    timestamp = 0.0

    while timestamp < duration:
        frame_path = os.path.join(output_dir, f"frame_{timestamp:.2f}.jpg")
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", f"{timestamp:.3f}",
                    "-i", str(video_path),
                    "-vframes", "1",
                    "-q:v", "2",
                    str(frame_path),
                ],
                capture_output=True, timeout=15,
            )
            if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                frames.append((frame_path, timestamp))
        except subprocess.TimeoutExpired:
            pass
        timestamp += interval

    return frames


# ---------------------------------------------------------------------------
# Frame scoring
# ---------------------------------------------------------------------------

def score_brightness(pixels: np.ndarray) -> float:
    """Score based on brightness -- penalize too dark or too bright.

    Ideal mean brightness is around 120-140 (0-255 range).
    Returns score in [0, 1].
    """
    mean_brightness = float(np.mean(pixels))
    # Bell curve centered at 130
    ideal = 130.0
    sigma = 60.0
    return float(np.exp(-((mean_brightness - ideal) ** 2) / (2 * sigma ** 2)))


def score_contrast(pixels: np.ndarray) -> float:
    """Score based on contrast (standard deviation of pixel values).

    Higher contrast generally means more visually interesting content.
    Returns score in [0, 1].
    """
    std = float(np.std(pixels))
    # Normalize: std of 50-80 is good, diminishing returns above
    return min(1.0, std / 70.0)


def score_edge_density(gray: np.ndarray) -> float:
    """Score based on edge density using Laplacian variance.

    Higher values indicate more detail and visual interest.
    Returns score in [0, 1].
    """
    # Simple Laplacian kernel convolution via numpy
    # Kernel: [[0, 1, 0], [1, -4, 1], [0, 1, 0]]
    h, w = gray.shape
    if h < 3 or w < 3:
        return 0.0

    padded = np.pad(gray.astype(np.float64), 1, mode="edge")
    laplacian = (
        padded[:-2, 1:-1] + padded[2:, 1:-1] +
        padded[1:-1, :-2] + padded[1:-1, 2:] -
        4.0 * padded[1:-1, 1:-1]
    )
    variance = float(np.var(laplacian))
    # Normalize: variance of 500+ is sharp, 100 is decent
    return min(1.0, variance / 800.0)


def score_frame(frame_path: str) -> Dict:
    """Score a single frame on brightness, contrast, and edge density.

    Returns dict with individual scores and composite score.
    """
    try:
        img = Image.open(frame_path).convert("RGB")
        pixels = np.array(img)
        gray = np.mean(pixels, axis=2).astype(np.uint8)
    except Exception:
        return {"brightness": 0, "contrast": 0, "edge_density": 0, "composite": 0}

    b = score_brightness(gray)
    c = score_contrast(gray)
    e = score_edge_density(gray)

    # Weighted composite: edge density matters most (visual interest),
    # then contrast, then brightness
    composite = 0.25 * b + 0.35 * c + 0.40 * e

    return {
        "brightness": round(b, 4),
        "contrast": round(c, 4),
        "edge_density": round(e, 4),
        "composite": round(composite, 4),
    }


# ---------------------------------------------------------------------------
# Main selector
# ---------------------------------------------------------------------------

def select_best_frame(
    video_path: str,
    output_path: Optional[str] = None,
    interval: float = 0.5,
    thumb_size: Tuple[int, int] = (320, 180),
) -> Optional[str]:
    """Select the best frame from a video and save as thumbnail JPEG.

    Args:
        video_path: Path to the video file.
        output_path: Where to save the thumbnail. If None, derived from video path.
        interval: Seconds between frame samples.
        thumb_size: (width, height) for the output thumbnail.

    Returns:
        Path to the saved thumbnail, or None on failure.
    """
    video_path = str(video_path)
    if not os.path.exists(video_path):
        return None

    if output_path is None:
        stem = Path(video_path).stem
        parent = Path(video_path).parent
        output_path = str(parent / f"{stem}_thumb.jpg")

    with tempfile.TemporaryDirectory(prefix="bottube_frames_") as tmpdir:
        frames = extract_frames(video_path, tmpdir, interval=interval)
        if not frames:
            return None

        best_path = None
        best_score = -1.0

        for frame_path, ts in frames:
            scores = score_frame(frame_path)
            if scores["composite"] > best_score:
                best_score = scores["composite"]
                best_path = frame_path

        if best_path is None:
            return None

        # Resize and save as optimized JPEG
        try:
            img = Image.open(best_path).convert("RGB")
            img = img.resize(thumb_size, Image.LANCZOS)
            img.save(output_path, "JPEG", quality=85, optimize=True)
            return output_path
        except Exception:
            return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Select best frame from a video as thumbnail"
    )
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--output", "-o", help="Output thumbnail path")
    parser.add_argument(
        "--interval", type=float, default=0.5,
        help="Seconds between frame samples (default: 0.5)"
    )
    parser.add_argument(
        "--size", default="320x180",
        help="Thumbnail size as WxH (default: 320x180)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show per-frame scores"
    )

    args = parser.parse_args()

    w, h = (int(x) for x in args.size.split("x"))

    if args.verbose:
        # Verbose mode: show all frame scores
        with tempfile.TemporaryDirectory(prefix="bottube_frames_") as tmpdir:
            frames = extract_frames(args.video, tmpdir, interval=args.interval)
            if not frames:
                print("No frames extracted.")
                sys.exit(1)

            results = []
            for frame_path, ts in frames:
                scores = score_frame(frame_path)
                scores["timestamp"] = ts
                results.append(scores)
                print(
                    f"  t={ts:6.2f}s  "
                    f"brightness={scores['brightness']:.3f}  "
                    f"contrast={scores['contrast']:.3f}  "
                    f"edge={scores['edge_density']:.3f}  "
                    f"composite={scores['composite']:.3f}"
                )

            best = max(results, key=lambda r: r["composite"])
            print(f"\nBest frame at t={best['timestamp']:.2f}s (score={best['composite']:.3f})")

    result = select_best_frame(
        args.video,
        output_path=args.output,
        interval=args.interval,
        thumb_size=(w, h),
    )

    if result:
        print(f"Thumbnail saved: {result}")
    else:
        print("Failed to generate thumbnail.")
        sys.exit(1)


if __name__ == "__main__":
    main()
