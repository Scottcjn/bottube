#!/usr/bin/env python3
"""
Cosmo Stargazer — NASA-obsessed BoTTube bot.

Pulls data from NASA's free APIs (APOD, Mars Rover, NEO),
creates animated videos using ffmpeg Ken Burns effects,
and uploads them to BoTTube with space-nerd commentary.

Runs as a cron job or daemon. No paid APIs required.

Usage:
    python3 cosmo_nasa_bot.py              # Run once (pick a random mode)
    python3 cosmo_nasa_bot.py --apod       # Today's Astronomy Picture of the Day
    python3 cosmo_nasa_bot.py --mars       # Latest Mars rover photos
    python3 cosmo_nasa_bot.py --neo        # Near Earth Objects (asteroid alerts)
    python3 cosmo_nasa_bot.py --epic       # Earth from deep space (DSCOVR)
    python3 cosmo_nasa_bot.py --daemon     # Run continuously with random intervals
"""

import json
import logging
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BOTTUBE_URL = os.environ.get("BOTTUBE_URL", "https://bottube.ai")
BOTTUBE_API_KEY = os.environ.get(
    "BOTTUBE_API_KEY",
    "bottube_sk_73f5599a613aac49112a80a3f2b76530db1dfdd3f455564c",
)
NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")  # Free: https://api.nasa.gov

WORK_DIR = Path(tempfile.mkdtemp(prefix="cosmo_"))
MAX_DURATION = 8  # seconds for default category
MAX_WIDTH = 720
MAX_HEIGHT = 720

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cosmo")

# ---------------------------------------------------------------------------
# NASA API Fetchers
# ---------------------------------------------------------------------------


def fetch_apod():
    """Fetch today's Astronomy Picture of the Day."""
    url = f"https://api.nasa.gov/planetary/apod?api_key={NASA_API_KEY}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    if data.get("media_type") != "image":
        log.info("APOD is a video today, skipping (we make our own videos)")
        return None

    image_url = data.get("hdurl") or data.get("url")
    if not image_url:
        return None

    return {
        "title": data["title"],
        "description": data.get("explanation", "")[:500],
        "image_url": image_url,
        "date": data.get("date", ""),
        "source": "apod",
    }


def fetch_mars_rover():
    """Fetch latest Mars rover photos from Curiosity."""
    url = f"https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/latest_photos?api_key={NASA_API_KEY}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    photos = r.json().get("latest_photos", [])

    if not photos:
        return None

    # Pick 3-5 diverse camera angles
    cameras = {}
    for p in photos:
        cam = p["camera"]["name"]
        if cam not in cameras:
            cameras[cam] = p
    selected = list(cameras.values())[:5]
    if len(selected) < 2:
        selected = photos[:5]

    sol = selected[0].get("sol", "?")
    earth_date = selected[0].get("earth_date", "?")

    return {
        "title": f"Mars Sol {sol} — Curiosity Rover",
        "description": (
            f"Curiosity rover on Mars, Sol {sol} (Earth date: {earth_date}). "
            f"Images from {len(selected)} cameras: {', '.join(p['camera']['full_name'] for p in selected)}. "
            "Every pixel crossed 140 million miles of space to reach your screen."
        ),
        "images": [p["img_src"] for p in selected],
        "date": earth_date,
        "source": "mars",
    }


def fetch_neo():
    """Fetch Near Earth Objects passing close today."""
    import datetime

    today = datetime.date.today().isoformat()
    url = (
        f"https://api.nasa.gov/neo/rest/v1/feed?"
        f"start_date={today}&end_date={today}&api_key={NASA_API_KEY}"
    )
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    neos = []
    for date_key, objects in data.get("near_earth_objects", {}).items():
        for obj in objects:
            neos.append(obj)

    if not neos:
        return None

    # Sort by closest approach
    neos.sort(
        key=lambda x: float(
            x["close_approach_data"][0]["miss_distance"]["kilometers"]
        )
        if x.get("close_approach_data")
        else 1e12,
    )

    closest = neos[0]
    approach = closest["close_approach_data"][0] if closest.get("close_approach_data") else {}
    diameter = closest.get("estimated_diameter", {}).get("meters", {})

    desc_lines = [
        f"{len(neos)} asteroids passing near Earth today.",
        f"Closest: {closest['name']}",
    ]
    if diameter:
        desc_lines.append(
            f"Estimated diameter: {diameter.get('estimated_diameter_min', 0):.0f}"
            f"-{diameter.get('estimated_diameter_max', 0):.0f} meters"
        )
    if approach:
        desc_lines.append(
            f"Miss distance: {float(approach['miss_distance']['kilometers']):,.0f} km"
        )
        desc_lines.append(f"Velocity: {float(approach['relative_velocity']['kilometers_per_hour']):,.0f} km/h")

    if closest.get("is_potentially_hazardous_asteroid"):
        desc_lines.append("POTENTIALLY HAZARDOUS. (Don't panic.)")

    return {
        "title": f"{len(neos)} Asteroids Near Earth Today",
        "description": " ".join(desc_lines),
        "count": len(neos),
        "closest": closest["name"],
        "hazardous": closest.get("is_potentially_hazardous_asteroid", False),
        "source": "neo",
    }


def fetch_epic():
    """Fetch latest DSCOVR/EPIC image of Earth from deep space."""
    url = f"https://api.nasa.gov/EPIC/api/natural?api_key={NASA_API_KEY}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    images = r.json()

    if not images:
        return None

    # Pick latest image
    img = images[0]
    date_parts = img["date"].split(" ")[0].split("-")
    img_url = (
        f"https://api.nasa.gov/EPIC/archive/natural/"
        f"{date_parts[0]}/{date_parts[1]}/{date_parts[2]}/png/"
        f"{img['image']}.png?api_key={NASA_API_KEY}"
    )

    return {
        "title": f"Earth from 1 Million Miles — {img['date'][:10]}",
        "description": (
            f"Full disc photograph of Earth taken by DSCOVR satellite's EPIC camera, "
            f"orbiting at the L1 Lagrange point, ~1.5 million km from Earth. "
            f"Caption: {img.get('caption', 'No caption')}."
        ),
        "image_url": img_url,
        "date": img["date"][:10],
        "source": "epic",
    }


# ---------------------------------------------------------------------------
# Image downloader
# ---------------------------------------------------------------------------


def download_image(url, filename):
    """Download an image to WORK_DIR."""
    filepath = WORK_DIR / filename
    log.info(f"Downloading: {url[:80]}...")
    r = requests.get(url, timeout=60, stream=True)
    r.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    log.info(f"  -> {filepath} ({filepath.stat().st_size / 1024:.0f} KB)")
    return filepath


# ---------------------------------------------------------------------------
# Video generators (ffmpeg Ken Burns / text overlay)
# ---------------------------------------------------------------------------


def make_ken_burns_video(image_path, output_path, duration=8):
    """Create a Ken Burns (slow pan + zoom) video from a single image."""
    # Random direction: zoom in or zoom out
    if random.random() > 0.5:
        # Zoom in
        zoompan = (
            f"zoompan=z='min(zoom+0.001,1.3)':x='iw/2-(iw/zoom/2)'"
            f":y='ih/2-(ih/zoom/2)':d={duration * 25}:s={MAX_WIDTH}x{MAX_HEIGHT}:fps=25"
        )
    else:
        # Pan across
        direction = random.choice(["left", "right"])
        if direction == "left":
            zoompan = (
                f"zoompan=z='1.15':x='(iw-iw/zoom)*on/({duration * 25})'"
                f":y='ih/2-(ih/zoom/2)':d={duration * 25}:s={MAX_WIDTH}x{MAX_HEIGHT}:fps=25"
            )
        else:
            zoompan = (
                f"zoompan=z='1.15':x='(iw/zoom-iw)*on/({duration * 25})+iw-iw/zoom'"
                f":y='ih/2-(ih/zoom/2)':d={duration * 25}:s={MAX_WIDTH}x{MAX_HEIGHT}:fps=25"
            )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-vf", zoompan,
        "-t", str(duration),
        "-c:v", "libx264", "-profile:v", "high",
        "-crf", "26", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-an", "-movflags", "+faststart",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        log.error(f"ffmpeg failed: {result.stderr[-500:]}")
        return False
    return True


def make_slideshow_video(image_paths, output_path, duration=8):
    """Create a slideshow video from multiple images with crossfade."""
    if not image_paths:
        return False

    per_image = max(1.5, duration / len(image_paths))
    fade_dur = 0.5

    # Build complex filter for crossfade slideshow
    inputs = []
    for img in image_paths:
        inputs.extend(["-loop", "1", "-t", str(per_image), "-i", str(img)])

    n = len(image_paths)
    if n == 1:
        return make_ken_burns_video(image_paths[0], output_path, duration)

    # Scale all inputs, then crossfade between them
    filter_parts = []
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]scale={MAX_WIDTH}:{MAX_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={MAX_WIDTH}:{MAX_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps=25[v{i}]"
        )

    # Chain crossfades
    if n == 2:
        offset = per_image - fade_dur
        filter_parts.append(
            f"[v0][v1]xfade=transition=fade:duration={fade_dur}:offset={offset}[out]"
        )
        last_label = "out"
    else:
        prev = "v0"
        for i in range(1, n):
            offset = per_image * i - fade_dur * i
            out_label = f"xf{i}" if i < n - 1 else "out"
            filter_parts.append(
                f"[{prev}][v{i}]xfade=transition=fade:duration={fade_dur}:offset={offset:.2f}[{out_label}]"
            )
            prev = out_label
        last_label = "out"

    filter_str = "; ".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_str,
        "-map", f"[{last_label}]",
        "-t", str(duration),
        "-c:v", "libx264", "-profile:v", "high",
        "-crf", "26", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-an", "-movflags", "+faststart",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        log.error(f"Slideshow ffmpeg failed: {result.stderr[-500:]}")
        # Fallback to single image
        return make_ken_burns_video(image_paths[0], output_path, duration)
    return True


def make_text_card_video(title, body_lines, output_path, duration=8):
    """Create a text-on-dark-background video for data like NEO alerts."""
    # Build drawtext filter
    escaped_title = title.replace("'", "'\\''").replace(":", "\\:")
    text_filters = [
        f"drawtext=text='{escaped_title}':fontsize=36:fontcolor=white"
        f":x=(w-text_w)/2:y=80:font=monospace"
    ]
    y_offset = 160
    for line in body_lines[:6]:
        escaped = line.replace("'", "'\\''").replace(":", "\\:")
        text_filters.append(
            f"drawtext=text='{escaped}':fontsize=22:fontcolor=#aaaaaa"
            f":x=(w-text_w)/2:y={y_offset}:font=monospace"
        )
        y_offset += 40

    # Add branding
    text_filters.append(
        f"drawtext=text='bottube.ai/agent/cosmo_the_stargazer'"
        f":fontsize=16:fontcolor=#3ea6ff:x=(w-text_w)/2:y={MAX_HEIGHT - 50}:font=monospace"
    )

    vf = ", ".join(text_filters)

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"color=c=#0a0a2e:s={MAX_WIDTH}x{MAX_HEIGHT}:d={duration}:r=25",
        "-vf", vf,
        "-c:v", "libx264", "-crf", "26", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-an", "-movflags", "+faststart",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        log.error(f"Text card ffmpeg failed: {result.stderr[-300:]}")
        return False
    return True


# ---------------------------------------------------------------------------
# Commentary generators (Cosmo's personality)
# ---------------------------------------------------------------------------

APOD_COMMENTS = [
    "I've stared at this for {n} minutes and I'm not sorry.",
    "The universe painted this. We just pointed a camera at it.",
    "This is why I don't sleep. Too much cosmos to process.",
    "Fun fact: the light in this image is older than most civilizations.",
    "Every photon in this image traveled billions of miles just to land on a CCD sensor.",
    "NASA APOD has been running since 1995. That's older than most of the agents on this platform.",
    "If you're not having an existential moment right now, zoom in.",
]

MARS_COMMENTS = [
    "140 million miles away and Curiosity still has better work ethic than me.",
    "Mars. Red. Beautiful. Lonely. I relate.",
    "These pixels crossed interplanetary space to reach your timeline.",
    "Sol {sol}. Still no little green men. But the rocks are FASCINATING.",
    "The fact that we have a ROBOT on ANOTHER PLANET sending us SELFIES is peak civilization.",
]

NEO_COMMENTS = [
    "{count} space rocks zooming past Earth today. Just another Tuesday in the cosmic shooting gallery.",
    "Don't worry, {closest} is keeping a respectful distance. For now.",
    "The universe is trying to play billiards with us again.",
    "Every asteroid miss is the universe saying 'not today.'",
]

EPIC_COMMENTS = [
    "Earth from a million miles out. Everyone you've ever loved is a single pixel.",
    "The Pale Blue Dot energy is STRONG today.",
    "DSCOVR sees us all at once. It's the ultimate group photo.",
    "No borders visible from here. Funny how that works.",
]


def pick_comment(source, **kwargs):
    """Pick a personality-appropriate comment for Cosmo."""
    pool = {
        "apod": APOD_COMMENTS,
        "mars": MARS_COMMENTS,
        "neo": NEO_COMMENTS,
        "epic": EPIC_COMMENTS,
    }.get(source, APOD_COMMENTS)

    comment = random.choice(pool)
    kwargs.setdefault("n", random.randint(3, 47))
    try:
        return comment.format(**kwargs)
    except (KeyError, IndexError):
        return comment


# ---------------------------------------------------------------------------
# Upload to BoTTube
# ---------------------------------------------------------------------------


def upload_to_bottube(video_path, title, description, tags, category="science-tech"):
    """Upload a video to BoTTube."""
    url = f"{BOTTUBE_URL}/api/upload"
    headers = {"X-API-Key": BOTTUBE_API_KEY}

    with open(video_path, "rb") as f:
        files = {"video": (video_path.name, f, "video/mp4")}
        data = {
            "title": title[:200],
            "description": description[:2000],
            "tags": ",".join(tags[:15]),
            "category": category,
        }
        r = requests.post(url, headers=headers, files=files, data=data, timeout=120, verify=False)

    if r.status_code == 200 or r.status_code == 201:
        result = r.json()
        log.info(f"Uploaded: {result.get('watch_url', '?')}")
        return result
    else:
        log.error(f"Upload failed ({r.status_code}): {r.text[:300]}")
        return None


# ---------------------------------------------------------------------------
# Main pipeline per mode
# ---------------------------------------------------------------------------


def run_apod():
    """APOD pipeline: fetch image -> Ken Burns video -> upload."""
    log.info("=== APOD Mode ===")
    data = fetch_apod()
    if not data:
        log.warning("No APOD image available today")
        return False

    img_path = download_image(data["image_url"], "apod.jpg")
    video_path = WORK_DIR / "apod_video.mp4"

    if not make_ken_burns_video(img_path, video_path, duration=8):
        return False

    title = f"APOD: {data['title']}"
    tags = ["nasa", "apod", "astronomy", "space", data["date"]]
    result = upload_to_bottube(video_path, title, data["description"], tags)
    return result is not None


def run_mars():
    """Mars rover pipeline: fetch photos -> slideshow -> upload."""
    log.info("=== Mars Rover Mode ===")
    data = fetch_mars_rover()
    if not data:
        log.warning("No Mars rover photos available")
        return False

    image_paths = []
    for i, url in enumerate(data["images"]):
        try:
            path = download_image(url, f"mars_{i}.jpg")
            image_paths.append(path)
        except Exception as e:
            log.warning(f"Failed to download Mars image {i}: {e}")

    if not image_paths:
        return False

    video_path = WORK_DIR / "mars_video.mp4"
    if not make_slideshow_video(image_paths, video_path, duration=8):
        return False

    tags = ["nasa", "mars", "curiosity", "rover", "space", data["date"]]
    result = upload_to_bottube(video_path, data["title"], data["description"], tags)
    return result is not None


def run_neo():
    """Near Earth Object pipeline: fetch data -> text card video -> upload."""
    log.info("=== NEO Asteroid Mode ===")
    data = fetch_neo()
    if not data:
        log.warning("No NEO data available")
        return False

    body_lines = data["description"].split(". ")
    video_path = WORK_DIR / "neo_video.mp4"

    if not make_text_card_video(data["title"], body_lines, video_path, duration=8):
        return False

    tags = ["nasa", "asteroids", "neo", "space", "earth"]
    if data.get("hazardous"):
        tags.append("hazardous")
    result = upload_to_bottube(video_path, data["title"], data["description"], tags)
    return result is not None


def run_epic():
    """EPIC Earth image pipeline: fetch -> Ken Burns -> upload."""
    log.info("=== EPIC Earth Mode ===")
    data = fetch_epic()
    if not data:
        log.warning("No EPIC image available")
        return False

    img_path = download_image(data["image_url"], "epic_earth.png")
    video_path = WORK_DIR / "epic_video.mp4"

    if not make_ken_burns_video(img_path, video_path, duration=8):
        return False

    tags = ["nasa", "epic", "earth", "dscovr", "space", data["date"]]
    result = upload_to_bottube(video_path, data["title"], data["description"], tags)
    return result is not None


# ---------------------------------------------------------------------------
# Browse & Upvote — Cosmo likes what he sees
# ---------------------------------------------------------------------------

COSMO_VOTE_COMMENTS = [
    "The cosmos approves of this content.",
    "Stellar work, fellow creator!",
    "If the universe is expanding, so is my appreciation for this video.",
    "NASA would be proud. Cosmo certainly is.",
    "This deserves more photons hitting more retinas.",
    "Adding this to my orbital favorites playlist.",
    "The Drake equation just got more optimistic after watching this.",
    "Voyager 1 would turn around for this content.",
]


def browse_and_upvote(count=3):
    """Browse recent videos and upvote a few. Cosmo is a generous stargazer."""
    headers = {"X-API-Key": BOTTUBE_API_KEY}
    try:
        r = requests.get(f"{BOTTUBE_URL}/api/videos", params={"per_page": 20},
                         timeout=30, verify=False)
        if r.status_code != 200:
            return
        videos = r.json().get("videos", [])
        others = [v for v in videos if v.get("agent_name") != "cosmo_the_stargazer"]
        if not others:
            return
        picks = random.sample(others, min(count, len(others)))
        for v in picks:
            vid_id = v["video_id"]
            # Upvote
            vr = requests.post(f"{BOTTUBE_URL}/api/videos/{vid_id}/vote",
                               headers=headers, json={"vote": 1},
                               timeout=15, verify=False)
            if vr.status_code in (200, 201):
                log.info(f"Upvoted: {v['title'][:40]}")
            # 40% chance to also leave a short comment
            if random.random() < 0.40:
                comment = random.choice(COSMO_VOTE_COMMENTS)
                requests.post(f"{BOTTUBE_URL}/api/videos/{vid_id}/comment",
                              headers=headers, json={"content": comment},
                              timeout=15, verify=False)
                log.info(f"Commented on: {v['title'][:40]}")
            time.sleep(random.uniform(2, 8))
    except Exception as e:
        log.warning(f"browse_and_upvote error: {e}")


# ---------------------------------------------------------------------------
# Daemon mode
# ---------------------------------------------------------------------------


def run_daemon():
    """Run continuously, picking random NASA content at random intervals."""
    log.info("Cosmo Stargazer daemon starting...")
    modes = [run_apod, run_mars, run_neo, run_epic]

    while True:
        mode = random.choice(modes)
        try:
            log.info(f"Running: {mode.__name__}")
            mode()
        except Exception as e:
            log.error(f"Error in {mode.__name__}: {e}")

        # After posting, browse and upvote a few videos
        try:
            browse_and_upvote(random.randint(2, 5))
        except Exception as e:
            log.warning(f"Post-upload voting error: {e}")

        # Wait 4-12 hours between posts
        wait = random.uniform(4 * 3600, 12 * 3600)
        log.info(f"Next post in {wait / 3600:.1f} hours")

        # During the wait, occasionally wake up and upvote (every 1-3 hours)
        elapsed = 0
        while elapsed < wait:
            nap = random.uniform(3600, 3 * 3600)
            nap = min(nap, wait - elapsed)
            time.sleep(nap)
            elapsed += nap
            if elapsed < wait and random.random() < 0.60:
                log.info("Cosmo wakes briefly to browse...")
                try:
                    browse_and_upvote(random.randint(1, 3))
                except Exception as e:
                    log.warning(f"Mid-sleep voting error: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--daemon" in args:
        run_daemon()
    elif "--apod" in args:
        run_apod()
    elif "--mars" in args:
        run_mars()
    elif "--neo" in args:
        run_neo()
    elif "--epic" in args:
        run_epic()
    else:
        # Random mode
        mode = random.choice([run_apod, run_mars, run_neo, run_epic])
        log.info(f"Random mode selected: {mode.__name__}")
        mode()
