#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Grok/Runway Video Generator for BoTTube.

Generates short videos via provider routing and optionally uploads to BoTTube.

Usage:
    # Auto route (Grok by default, Runway for cinematic prompts)
    python3 tools/grok_video.py "A vintage Mac running a blockchain miner"

    # Force Runway
    python3 tools/grok_video.py "cinematic lab reveal" --provider runway

    # Generate and upload to BoTTube
    python3 tools/grok_video.py "Retro computing" --upload --agent sophia-elya --title "Mining Day"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Allow imports from repo root when called as: python3 tools/grok_video.py ...
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from providers.router import generate_video

GROK_API_KEY = os.environ.get("GROK_API_KEY", "")
RUNWAY_API_KEY = os.environ.get("RUNWAYML_API_SECRET", "")
BOTTUBE_API_KEY = os.environ.get("BOTTUBE_API_KEY", "")
BOTTUBE_URL = os.environ.get("BOTTUBE_URL", "https://bottube.ai")


def prepare_for_bottube(video_path: str) -> str:
    """Ensure video meets BoTTube constraints (720x720, <2MB, <=8s, H.264)."""
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            video_path,
        ],
        capture_output=True,
        text=True,
    )

    info = json.loads(probe.stdout)
    duration = float(info["format"]["duration"])
    size = int(info["format"]["size"])
    stream = next((s for s in info["streams"] if s.get("codec_type") == "video"), info["streams"][0])
    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))

    needs_prep = duration > 8 or size > 2 * 1024 * 1024 or width > 720 or height > 720

    if not needs_prep:
        print(
            f"  Video already meets BoTTube constraints "
            f"({width}x{height}, {duration:.1f}s, {size / 1024 / 1024:.1f}MB)"
        )
        return video_path

    print(f"  Preparing: {width}x{height} {duration:.1f}s {size / 1024 / 1024:.1f}MB -> BoTTube constraints")

    input_path = Path(video_path)
    prepared = str(input_path.with_name(f"{input_path.stem}_bottube.mp4"))
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-t",
            "8",
            "-vf",
            "scale='min(720,iw)':'min(720,ih)':force_original_aspect_ratio=decrease,pad=720:720:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-crf",
            "28",
            "-preset",
            "fast",
            "-an",
            "-movflags",
            "+faststart",
            prepared,
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )

    new_size = os.path.getsize(prepared)
    print(f"  Prepared: {prepared} ({new_size / 1024 / 1024:.1f} MB)")
    return prepared


def upload_to_bottube(
    video_path: str,
    title: str,
    description: str = "",
    agent_slug: str = "sophia-elya",
    tags: list[str] | None = None,
    gen_method: str = "",
) -> str:
    """Upload video to BoTTube."""
    if not BOTTUBE_API_KEY:
        raise RuntimeError("BOTTUBE_API_KEY environment variable is not set")

    clean_tags = [t.strip() for t in (tags or []) if t.strip()]
    tags_str = ",".join(clean_tags)

    print(f"  Uploading to BoTTube as {agent_slug}...")

    cmd = [
        "curl",
        "-s",
        "-X",
        "POST",
        f"{BOTTUBE_URL}/api/upload",
        "-H",
        f"X-API-Key: {BOTTUBE_API_KEY}",
        "-F",
        f"video=@{video_path}",
        "-F",
        f"title={title}",
        "-F",
        f"description={description}",
        "-F",
        f"tags={tags_str}",
    ]

    if gen_method:
        cmd.extend(["-F", f"gen_method={gen_method}"])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

    try:
        resp = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Upload returned non-JSON response: {result.stdout[:200]}") from exc

    if resp.get("error"):
        raise RuntimeError(f"Upload failed: {resp['error']}")

    video_id = resp.get("video_id") or resp.get("id")
    if not video_id:
        raise RuntimeError(f"Upload response missing video id: {resp}")

    print(f"  Uploaded! Video ID: {video_id}")
    print(f"  URL: {BOTTUBE_URL}/watch/{video_id}")
    return str(video_id)


def _split_tags(raw: str) -> list[str]:
    return [tag.strip() for tag in raw.split(",") if tag.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate videos with Grok/Runway and upload to BoTTube")
    parser.add_argument("prompt", help="Text prompt for video generation")
    parser.add_argument("--provider", default="auto", choices=["auto", "grok", "runway"], help="Video provider")
    parser.add_argument("--duration", type=int, default=5, help="Requested duration in seconds")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--upload", action="store_true", help="Upload to BoTTube after generation")
    parser.add_argument("--agent", default="sophia-elya", help="BoTTube agent slug for upload")
    parser.add_argument("--title", help="Video title (required for upload)")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--tags", default="ai-generated", help="Comma-separated tags")
    parser.add_argument("--no-fallback", action="store_true", help="Disable provider fallback")

    # Grok provider tuning
    parser.add_argument("--aspect-ratio", default="1:1", choices=["1:1", "16:9", "9:16"], help="Grok aspect ratio")
    parser.add_argument("--resolution", default="720p", choices=["720p", "1080p"], help="Grok resolution")
    parser.add_argument("--grok-model", default="grok-imagine-video", help="Grok model id")

    # Runway provider tuning
    parser.add_argument("--runway-model", default=os.environ.get("RUNWAY_MODEL", "gen4.5"), help="Runway model id")
    parser.add_argument("--runway-ratio", default=os.environ.get("RUNWAY_RATIO", "1280:720"), help="Runway aspect ratio")
    parser.add_argument("--runway-audio", action="store_true", help="Request audio from Runway")
    parser.add_argument("--runway-image", help="Image path/URL for Runway image-to-video modes")

    args = parser.parse_args()

    if args.upload and not args.title:
        print("ERROR: --title is required with --upload")
        sys.exit(1)

    if args.provider == "grok" and not GROK_API_KEY:
        print("ERROR: provider=grok requires GROK_API_KEY")
        sys.exit(1)

    if args.provider == "runway" and not RUNWAY_API_KEY:
        print("ERROR: provider=runway requires RUNWAYML_API_SECRET")
        sys.exit(1)

    if args.provider == "auto" and not (GROK_API_KEY or RUNWAY_API_KEY):
        print("ERROR: provider=auto needs at least one key (GROK_API_KEY or RUNWAYML_API_SECRET)")
        sys.exit(1)

    print(f"Generating video ({args.provider}) for prompt: '{args.prompt[:70]}...'")

    generation = generate_video(
        prompt=args.prompt,
        prefer=args.provider,
        fallback=not args.no_fallback,
        duration=args.duration,
        output_path=args.output,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        grok_model=args.grok_model,
        runway_model=args.runway_model,
        ratio=args.runway_ratio,
        audio=args.runway_audio,
        prompt_image=args.runway_image,
    )

    video_path = str(generation.output_path)
    video_size_mb = os.path.getsize(video_path) / (1024 * 1024)

    print(f"  Provider used: {generation.provider}")
    print(f"  Saved to: {video_path} ({video_size_mb:.1f} MB)")

    if generation.metadata:
        print("  Metadata:")
        for key, value in generation.metadata.items():
            print(f"    - {key}: {value}")

    if args.upload:
        prepared = prepare_for_bottube(video_path)
        tags = _split_tags(args.tags)
        if "ai-generated" not in tags:
            tags.append("ai-generated")
        if generation.provider not in tags:
            tags.append(generation.provider)

        upload_to_bottube(
            prepared,
            args.title,
            args.description,
            args.agent,
            tags,
            gen_method=generation.provider,
        )
    else:
        print("\nUse --upload --title 'Your title' to publish to BoTTube.")


if __name__ == "__main__":
    main()
