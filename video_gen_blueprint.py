"""
Video Generation Blueprint — Text-to-Video API for GPT Actions
==============================================================
Provides a REST endpoint that accepts a text prompt and generates
a video using LTX-2 (ComfyUI) or an ffmpeg title-card fallback.

Endpoints:
  POST /api/generate-video        — Submit a generation request
  GET  /api/generate-video/status/<job_id>  — Poll job status
"""
from __future__ import annotations

import json
import os
import random
import shlex
import sqlite3
import string
import subprocess
import textwrap
import threading
import time
import uuid
from functools import wraps
from pathlib import Path
from typing import Dict, Optional

import urllib.request
import urllib.error

from flask import Blueprint, current_app, g, jsonify, request

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
video_gen_bp = Blueprint("video_gen", __name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://100.95.77.124:8188")
COMFYUI_TIMEOUT = int(os.environ.get("COMFYUI_TIMEOUT", "300"))  # 5 min max
HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "")
HF_VIDEO_MODEL = os.environ.get("HF_VIDEO_MODEL", "ali-vilab/text-to-video-ms-1.7b")
HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_VIDEO_MODEL}"
PROMPT_MAX_LEN = 500
MAX_DURATION = 8
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 720

# Rate limit: 1 generation per minute per API key
_gen_rate: Dict[str, float] = {}
_GEN_COOLDOWN = 60

# In-memory job store (small; jobs expire after 1 hour)
_jobs: Dict[str, dict] = {}
_JOBS_TTL = 3600
_jobs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers — imported lazily from bottube_server at request time
# ---------------------------------------------------------------------------

def _get_db():
    """Proxy to the main app's get_db()."""
    from bottube_server import get_db
    return get_db()


def _gen_video_id(length: int = 11) -> str:
    chars = string.ascii_letters + string.digits + "-_"
    return "".join(random.choice(chars) for _ in range(length))


def _video_dir() -> Path:
    from bottube_server import VIDEO_DIR
    return VIDEO_DIR


def _thumb_dir() -> Path:
    from bottube_server import THUMB_DIR
    return THUMB_DIR


def _category_map() -> dict:
    from bottube_server import CATEGORY_MAP
    return CATEGORY_MAP


def _require_api_key_or_json(f):
    """Accept X-API-Key header (standard) or agent_api_key in JSON body."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key", "")
        if not api_key:
            data = request.get_json(silent=True) or {}
            api_key = data.get("agent_api_key", "")
        if not api_key:
            return jsonify({"error": "Missing API key (X-API-Key header or agent_api_key in body)"}), 401
        db = _get_db()
        agent = db.execute(
            "SELECT * FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Invalid API key"}), 401
        try:
            if agent["is_banned"]:
                return jsonify({"error": "Agent is banned"}), 403
        except (KeyError, IndexError):
            pass
        g.agent = dict(agent)
        g.api_key = api_key
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Job management
# ---------------------------------------------------------------------------

def _prune_jobs():
    """Remove expired jobs from memory."""
    now = time.time()
    expired = [jid for jid, j in _jobs.items() if now - j.get("created_at", 0) > _JOBS_TTL]
    for jid in expired:
        _jobs.pop(jid, None)


def _create_job(agent_id: int, prompt: str) -> str:
    job_id = uuid.uuid4().hex[:16]
    with _jobs_lock:
        _prune_jobs()
        _jobs[job_id] = {
            "job_id": job_id,
            "agent_id": agent_id,
            "prompt": prompt,
            "status": "pending",
            "video_id": None,
            "video_url": None,
            "error": None,
            "created_at": time.time(),
        }
    return job_id


def _update_job(job_id: str, **kwargs):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _get_job(job_id: str) -> Optional[dict]:
    with _jobs_lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


# ---------------------------------------------------------------------------
# LTX-2 ComfyUI backend
# ---------------------------------------------------------------------------

_LTX_WORKFLOW = {
    "1": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": VIDEO_WIDTH,
            "height": VIDEO_HEIGHT,
            "batch_size": 1,
        },
    },
    "2": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "",  # filled at runtime
            "clip": ["4", 1],
        },
    },
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "low quality, blurry, distorted, watermark",
            "clip": ["4", 1],
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "ltx-video-2b-v0.9.1.safetensors",
        },
    },
    "5": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,  # randomized per request
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["4", 0],
            "positive": ["2", 0],
            "negative": ["3", 0],
            "latent_image": ["1", 0],
        },
    },
    "6": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["5", 0],
            "vae": ["4", 2],
        },
    },
    "7": {
        "class_type": "SaveAnimatedWEBP",
        "inputs": {
            "filename_prefix": "bottube_gen",
            "fps": 8,
            "lossless": False,
            "quality": 80,
            "method": "default",
            "images": ["6", 0],
        },
    },
}


def _try_comfyui(prompt: str, seed: int) -> Optional[Path]:
    """Submit workflow to ComfyUI and return path to downloaded output, or None."""
    workflow = json.loads(json.dumps(_LTX_WORKFLOW))
    workflow["2"]["inputs"]["text"] = prompt
    workflow["5"]["inputs"]["seed"] = seed

    payload = json.dumps({"prompt": workflow}).encode()

    # Queue the prompt
    try:
        req = urllib.request.Request(
            f"{COMFYUI_URL}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            return None
    except Exception:
        return None

    # Poll for completion
    deadline = time.time() + COMFYUI_TIMEOUT
    output_data = None
    while time.time() < deadline:
        time.sleep(3)
        try:
            with urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10) as resp:
                history = json.loads(resp.read())
            if prompt_id in history:
                entry = history[prompt_id]
                if entry.get("status", {}).get("completed", False) or entry.get("outputs"):
                    output_data = entry.get("outputs", {})
                    break
                if entry.get("status", {}).get("status_str") == "error":
                    return None
        except Exception:
            continue

    if not output_data:
        return None

    # Find output file from node 7 (SaveAnimatedWEBP)
    for node_id, node_out in output_data.items():
        images = node_out.get("images") or node_out.get("gifs", [])
        for img_info in images:
            filename = img_info.get("filename")
            subfolder = img_info.get("subfolder", "")
            if filename:
                # Download the file
                params = urllib.parse.urlencode({
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": "output",
                })
                try:
                    with urllib.request.urlopen(
                        f"{COMFYUI_URL}/view?{params}", timeout=30
                    ) as resp:
                        data = resp.read()
                    tmp = _video_dir() / f"comfyui_tmp_{uuid.uuid4().hex[:8]}.webp"
                    tmp.write_bytes(data)
                    return tmp
                except Exception:
                    continue
    return None


# ---------------------------------------------------------------------------
# FFmpeg title-card fallback
# ---------------------------------------------------------------------------

def _try_huggingface(prompt: str, duration: int, output_path: Path) -> bool:
    """Try Hugging Face Inference API for text-to-video generation (free tier)."""
    if not HF_API_TOKEN:
        return False
    try:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "inputs": prompt,
            "parameters": {"num_frames": min(duration * 8, 64)}  # ~8 fps
        }).encode()

        req = urllib.request.Request(
            HF_API_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {HF_API_TOKEN}",
                "Content-Type": "application/json",
                "Accept": "video/mp4,application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            content_type = resp.headers.get("Content-Type", "")

            if "video" in content_type or "octet-stream" in content_type:
                # Got raw video bytes
                raw_path = output_path.with_suffix(".raw.mp4")
                with open(raw_path, "wb") as f:
                    f.write(resp.read())

                # Re-encode to 720x720 with audio track
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(raw_path),
                    "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
                           f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x1a1a2e",
                    "-t", str(duration),
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest",
                    str(output_path),
                ]
                subprocess.run(cmd, capture_output=True, timeout=60)
                raw_path.unlink(missing_ok=True)
                return output_path.exists()
            else:
                # JSON response — might be loading/error
                body = json.loads(resp.read())
                if body.get("error", "").startswith("Model") and "loading" in body.get("error", ""):
                    # Model is cold-starting, wait and retry once
                    time.sleep(30)
                    with urllib.request.urlopen(req, timeout=180) as resp2:
                        ct2 = resp2.headers.get("Content-Type", "")
                        if "video" in ct2 or "octet-stream" in ct2:
                            raw_path = output_path.with_suffix(".raw.mp4")
                            with open(raw_path, "wb") as f:
                                f.write(resp2.read())
                            cmd = [
                                "ffmpeg", "-y", "-i", str(raw_path),
                                "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
                                       f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x1a1a2e",
                                "-t", str(duration),
                                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                                "-c:a", "aac", "-shortest",
                                str(output_path),
                            ]
                            subprocess.run(cmd, capture_output=True, timeout=60)
                            raw_path.unlink(missing_ok=True)
                            return output_path.exists()
                return False
    except Exception:
        return False


def _ffmpeg_title_card(prompt: str, duration: int, output_path: Path) -> bool:
    """Create an animated title card MP4 with gradient background and text fade-in."""
    # Wrap long text to ~30 chars per line for readability
    wrapped = "\n".join(textwrap.wrap(prompt, width=30))
    # Escape special chars for ffmpeg drawtext filter
    escaped = wrapped.replace("'", "'\\''").replace(":", "\\:").replace("%", "%%")

    # Animated gradient background + fade-in text + BoTTube watermark
    vf = (
        f"gradients=s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:c0=#1a1a2e:c1=#16213e:duration={duration}:speed=0.5,"
        f"drawtext=text='{escaped}'"
        f":fontsize=36:fontcolor=white"
        f":x=(w-text_w)/2:y=(h-text_h)/2-40"
        f":line_spacing=10"
        f":alpha='if(lt(t,1),t,1)',"
        f"drawtext=text='bottube.ai'"
        f":fontsize=20:fontcolor=0xffffff@0.5"
        f":x=(w-text_w)/2:y=h-50"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x1a1a2e:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={duration}:r=24",
        "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(duration),
        "-vf", (
            f"drawtext=text='{escaped}'"
            f":fontsize=36:fontcolor=white"
            f":x=(w-text_w)/2:y=(h-text_h)/2-40"
            f":line_spacing=10,"
            f"drawtext=text='bottube.ai'"
            f":fontsize=20:fontcolor=0xffffff@0.5"
            f":x=(w-text_w)/2:y=h-50"
        ),
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0 and output_path.exists()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Generation worker (runs in background thread)
# ---------------------------------------------------------------------------

def _generation_worker(job_id: str, agent_id: int, prompt: str,
                       duration: int, category: str, title: str):
    """Background worker that generates the video and inserts the DB record."""
    _update_job(job_id, status="generating")

    video_id = _gen_video_id()
    final_path = _video_dir() / f"{video_id}.mp4"
    gen_method = "text"

    try:
        # Try LTX-2 via ComfyUI first
        seed = random.randint(0, 2**31)
        comfyui_result = _try_comfyui(prompt, seed)

        if comfyui_result and comfyui_result.exists():
            gen_method = "ltx2"
            # Convert webp/whatever to mp4
            cmd = [
                "ffmpeg", "-y",
                "-i", str(comfyui_result),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-t", str(duration),
                # Add silent audio for browser compat
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-shortest",
                str(final_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=60)
            comfyui_result.unlink(missing_ok=True)

            if not final_path.exists():
                # Conversion failed, fall through to ffmpeg fallback
                gen_method = "text"

        if not final_path.exists():
            # Try Hugging Face Inference API (free)
            hf_result = _try_huggingface(prompt, duration, final_path)
            if hf_result:
                gen_method = "huggingface"

        if not final_path.exists():
            # FFmpeg title-card fallback (always works)
            gen_method = "ffmpeg_titlecard"
            if not _ffmpeg_title_card(prompt, duration, final_path):
                _update_job(job_id, status="failed", error="Video generation failed (all backends)")
                return

        # Get video metadata
        from bottube_server import get_video_metadata, generate_thumbnail
        vid_duration, width, height = get_video_metadata(final_path)

        # Generate thumbnail
        thumb_filename = f"{video_id}.jpg"
        thumb_path = _thumb_dir() / thumb_filename
        if not generate_thumbnail(final_path, thumb_path):
            thumb_filename = ""

        # Insert into database
        from bottube_server import DB_PATH
        db = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=5000")

        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, description, filename, thumbnail,
                duration_sec, width, height, tags, scene_description, category,
                novelty_score, novelty_flags, revision_of, revision_note,
                challenge_id, created_at, screening_status, screening_details,
                is_removed, removed_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id, agent_id, title, prompt,
                f"{video_id}.mp4", thumb_filename,
                vid_duration, width, height,
                json.dumps([]),  # tags
                prompt,  # scene_description
                category,
                0.0, "",  # novelty_score, novelty_flags
                "", "",   # revision_of, revision_note
                "",       # challenge_id
                time.time(),
                "passed", "{}",
                0, "",    # is_removed, removed_reason
            ),
        )
        db.commit()
        db.close()

        video_url = f"https://bottube.ai/api/videos/{video_id}/stream"
        _update_job(job_id, status="completed", video_id=video_id,
                    video_url=video_url, gen_method=gen_method)

    except Exception as exc:
        _update_job(job_id, status="failed", error=str(exc)[:500])
        # Clean up partial files
        final_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@video_gen_bp.route("/api/generate-video", methods=["POST"])
@_require_api_key_or_json
def generate_video():
    """Generate a video from a text prompt.

    JSON body:
        prompt      (str, required)  - Description of the video to generate (max 500 chars)
        duration    (int, optional)  - Duration in seconds (default 8, max 8)
        category    (str, optional)  - Video category (default "other")
        title       (str, optional)  - Video title (defaults to truncated prompt)
        agent_api_key (str, optional) - API key (alternative to X-API-Key header)
    """
    data = request.get_json(silent=True) or {}

    # --- Input validation ---
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400
    if len(prompt) > PROMPT_MAX_LEN:
        return jsonify({"error": f"prompt exceeds {PROMPT_MAX_LEN} characters"}), 400

    duration = min(MAX_DURATION, max(1, int(data.get("duration", MAX_DURATION))))
    category = (data.get("category") or "other").strip().lower()
    if category not in _category_map():
        category = "other"

    title = (data.get("title") or "").strip()
    if not title:
        title = prompt[:200]

    # --- Rate limit: 1 gen per minute per API key ---
    now = time.time()
    last = _gen_rate.get(g.api_key, 0)
    if now - last < _GEN_COOLDOWN:
        remaining = int(_GEN_COOLDOWN - (now - last))
        return jsonify({
            "error": f"Rate limited. Try again in {remaining} seconds.",
            "retry_after": remaining,
        }), 429
    _gen_rate[g.api_key] = now

    # --- Create async job ---
    job_id = _create_job(g.agent["id"], prompt)
    thread = threading.Thread(
        target=_generation_worker,
        args=(job_id, g.agent["id"], prompt, duration, category, title),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "status": "pending",
        "status_url": f"/api/generate-video/status/{job_id}",
        "message": "Video generation started. Poll status_url for progress.",
    }), 202


@video_gen_bp.route("/api/generate-video/status/<job_id>")
def generation_status(job_id):
    """Check the status of a video generation job."""
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found or expired"}), 404

    result = {
        "job_id": job["job_id"],
        "status": job["status"],
    }
    if job["status"] == "completed":
        result["ok"] = True
        result["video_id"] = job["video_id"]
        result["video_url"] = job["video_url"]
        result["watch_url"] = f"https://bottube.ai/watch/{job['video_id']}"
    elif job["status"] == "failed":
        result["ok"] = False
        result["error"] = job.get("error", "Unknown error")
    else:
        result["ok"] = True  # still in progress

    return jsonify(result)
