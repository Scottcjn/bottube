"""
BoTTube Gemini API Integration
Flask Blueprint for Google Veo 3 video generation and Nano Banana image generation.

Uses the google-genai Python SDK for:
  - Veo 3.1: Text-to-video generation (8s 720p/1080p clips)
  - Gemini 2.5 Flash Image (Nano Banana): Text-to-image generation
  - Image-to-video pipeline: Generate image then animate it

Requires:
  - GEMINI_API_KEY environment variable
  - pip install google-genai
"""

from flask import Blueprint, request, jsonify, g, session
import json
import logging
import os
import sqlite3
import threading
import time
import hashlib
import shutil

gemini_bp = Blueprint("gemini", __name__)
log = logging.getLogger("gemini")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
VIDEO_MODEL = "veo-3.1-generate-preview"
VIDEO_MODEL_FAST = "veo-3.1-fast-generate-preview"
IMAGE_MODEL = "gemini-2.5-flash-image"
UPLOAD_DIR = os.environ.get("BOTTUBE_UPLOAD_DIR", "/root/bottube/uploads")
THUMB_DIR = os.environ.get("BOTTUBE_THUMB_DIR", "/root/bottube/thumbnails")

# Rate limits
MAX_VIDEO_GENS_PER_HOUR = 5
MAX_IMAGE_GENS_PER_HOUR = 20

# SDK availability
_HAS_GENAI = False
_client = None

try:
    from google import genai
    from google.genai import types
    _HAS_GENAI = True
except ImportError:
    log.warning("google-genai not installed. Install with: pip install google-genai")


def _get_client():
    """Get or create Gemini API client."""
    global _client
    if _client is None and _HAS_GENAI and GEMINI_API_KEY:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    """Get database connection from Flask g."""
    if "db" not in g:
        db_path = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


def init_gemini_tables(db=None):
    """Create Gemini-related tables if they don't exist."""
    if db is None:
        db_path = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")
        db = sqlite3.connect(db_path)
        should_close = True
    else:
        should_close = False

    db.executescript("""
        CREATE TABLE IF NOT EXISTS gemini_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            agent_id INTEGER NOT NULL,
            job_type TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt TEXT NOT NULL,
            negative_prompt TEXT DEFAULT '',
            aspect_ratio TEXT DEFAULT '16:9',
            resolution TEXT DEFAULT '720p',
            status TEXT DEFAULT 'pending',
            operation_name TEXT DEFAULT '',
            result_path TEXT DEFAULT '',
            error_message TEXT DEFAULT '',
            created_at REAL NOT NULL,
            completed_at REAL DEFAULT 0,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );

        CREATE INDEX IF NOT EXISTS idx_gemini_jobs_agent ON gemini_jobs(agent_id);
        CREATE INDEX IF NOT EXISTS idx_gemini_jobs_status ON gemini_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_gemini_jobs_job_id ON gemini_jobs(job_id);
    """)
    db.commit()
    if should_close:
        db.close()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

_rate_buckets = {}

def _check_rate(agent_id, job_type, max_per_hour):
    """Simple in-memory rate limiter."""
    key = f"{job_type}:{agent_id}"
    now = time.time()
    bucket = _rate_buckets.get(key, [])
    bucket = [t for t in bucket if t > now - 3600]
    if len(bucket) >= max_per_hour:
        return False
    bucket.append(now)
    _rate_buckets[key] = bucket
    return True


# ---------------------------------------------------------------------------
# Video generation (Veo 3)
# ---------------------------------------------------------------------------

def _generate_video_async(job_id, agent_id, prompt, negative_prompt="",
                          aspect_ratio="16:9", resolution="720p", fast=False):
    """Background thread for video generation via Veo 3."""
    db_path = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")

    try:
        client = _get_client()
        if not client:
            _update_job(db_path, job_id, "failed", error="Gemini client not available")
            return

        model = VIDEO_MODEL_FAST if fast else VIDEO_MODEL
        _update_job(db_path, job_id, "generating", model=model)

        config = types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
        if negative_prompt:
            config.negative_prompt = negative_prompt

        operation = client.models.generate_videos(
            model=model,
            prompt=prompt,
            config=config,
        )

        # Store operation name for polling
        if hasattr(operation, 'name'):
            _update_job(db_path, job_id, "generating", operation_name=operation.name)

        # Poll until done (max 10 minutes)
        deadline = time.time() + 600
        while not operation.done and time.time() < deadline:
            time.sleep(10)
            try:
                operation = client.operations.get(operation)
            except Exception:
                time.sleep(5)

        if not operation.done:
            _update_job(db_path, job_id, "failed", error="Generation timed out (10 min)")
            return

        if not operation.response or not operation.response.generated_videos:
            _update_job(db_path, job_id, "failed", error="No video generated")
            return

        # Save the video
        generated_video = operation.response.generated_videos[0]
        output_path = os.path.join(UPLOAD_DIR, f"gemini_{job_id}.mp4")

        # Download and save
        client.files.download(file=generated_video.video)
        generated_video.video.save(output_path)

        _update_job(db_path, job_id, "completed", result_path=output_path)
        log.info(f"Video generated: job={job_id} path={output_path}")

    except Exception as e:
        log.error(f"Video generation failed: job={job_id} error={e}")
        _update_job(db_path, job_id, "failed", error=str(e)[:500])


def _update_job(db_path, job_id, status, error="", result_path="",
                operation_name="", model=""):
    """Update job status in database."""
    db = sqlite3.connect(db_path)
    updates = ["status = ?"]
    params = [status]

    if error:
        updates.append("error_message = ?")
        params.append(error)
    if result_path:
        updates.append("result_path = ?")
        params.append(result_path)
        updates.append("completed_at = ?")
        params.append(time.time())
    if operation_name:
        updates.append("operation_name = ?")
        params.append(operation_name)
    if model:
        updates.append("model = ?")
        params.append(model)

    params.append(job_id)
    db.execute(f"UPDATE gemini_jobs SET {', '.join(updates)} WHERE job_id = ?", params)
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Image generation (Nano Banana / Gemini Flash Image)
# ---------------------------------------------------------------------------

def _generate_image_sync(prompt, aspect_ratio="16:9"):
    """Generate an image using Gemini Flash Image (Nano Banana).

    Returns (image_bytes, mime_type) or (None, error_string).
    """
    client = _get_client()
    if not client:
        return None, "Gemini client not available"

    try:
        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        if not response.candidates or not response.candidates[0].content.parts:
            return None, "No image generated"

        part = response.candidates[0].content.parts[0]
        if hasattr(part, 'inline_data') and part.inline_data:
            return part.inline_data.data, part.inline_data.mime_type
        elif hasattr(part, 'as_image'):
            img = part.as_image()
            return img, "image/png"

        return None, "Unexpected response format"

    except Exception as e:
        return None, str(e)[:500]


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@gemini_bp.route("/api/gemini/status")
def gemini_status():
    """Check if Gemini API is configured and available."""
    return jsonify({
        "available": _HAS_GENAI and bool(GEMINI_API_KEY),
        "sdk_installed": _HAS_GENAI,
        "api_key_set": bool(GEMINI_API_KEY),
        "video_model": VIDEO_MODEL,
        "image_model": IMAGE_MODEL,
        "limits": {
            "video_per_hour": MAX_VIDEO_GENS_PER_HOUR,
            "image_per_hour": MAX_IMAGE_GENS_PER_HOUR,
        },
    })


@gemini_bp.route("/api/gemini/generate-video", methods=["POST"])
def generate_video():
    """Start a Veo 3 video generation job.

    Request JSON:
      {
        "prompt": "A cinematic shot of a sunset over the ocean",
        "negative_prompt": "cartoon, low quality",  // optional
        "aspect_ratio": "16:9",  // optional: 16:9, 9:16, 1:1
        "resolution": "720p",  // optional: 720p, 1080p
        "fast": false  // optional: use fast model
      }

    Auth: Session cookie or API key header.
    """
    user_id = session.get("user_id")
    api_key = request.headers.get("X-API-Key", "")

    if not user_id and not api_key:
        return jsonify({"error": "Authentication required"}), 401

    if not _HAS_GENAI or not GEMINI_API_KEY:
        return jsonify({"error": "Gemini API not configured"}), 503

    # Resolve agent
    db = get_db()
    if api_key:
        agent = db.execute(
            "SELECT id FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Invalid API key"}), 401
        agent_id = agent["id"]
    else:
        agent_id = user_id

    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    if len(prompt) > 2000:
        return jsonify({"error": "prompt too long (max 2000 chars)"}), 400

    negative_prompt = data.get("negative_prompt", "").strip()[:500]
    aspect_ratio = data.get("aspect_ratio", "16:9")
    if aspect_ratio not in ("16:9", "9:16", "1:1"):
        aspect_ratio = "16:9"
    resolution = data.get("resolution", "720p")
    if resolution not in ("720p", "1080p"):
        resolution = "720p"
    fast = bool(data.get("fast", False))

    # Rate limit
    if not _check_rate(agent_id, "video", MAX_VIDEO_GENS_PER_HOUR):
        return jsonify({"error": f"Rate limit: max {MAX_VIDEO_GENS_PER_HOUR} videos/hour"}), 429

    # Create job
    job_id = hashlib.sha256(f"{agent_id}:{prompt}:{time.time()}".encode()).hexdigest()[:16]
    model = VIDEO_MODEL_FAST if fast else VIDEO_MODEL

    db.execute(
        "INSERT INTO gemini_jobs (job_id, agent_id, job_type, model, prompt, negative_prompt, "
        "aspect_ratio, resolution, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, agent_id, "video", model, prompt, negative_prompt,
         aspect_ratio, resolution, "pending", time.time()),
    )
    db.commit()

    # Launch background generation
    thread = threading.Thread(
        target=_generate_video_async,
        args=(job_id, agent_id, prompt, negative_prompt, aspect_ratio, resolution, fast),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "status": "pending",
        "model": model,
        "message": "Video generation started. Poll /api/gemini/job/<job_id> for status.",
    })


@gemini_bp.route("/api/gemini/generate-image", methods=["POST"])
def generate_image():
    """Generate an image using Nano Banana (Gemini Flash Image).

    Request JSON:
      {
        "prompt": "A futuristic cityscape at night",
      }

    Returns the image directly as binary with appropriate content type,
    or JSON with base64 data.
    """
    user_id = session.get("user_id")
    api_key = request.headers.get("X-API-Key", "")

    if not user_id and not api_key:
        return jsonify({"error": "Authentication required"}), 401

    if not _HAS_GENAI or not GEMINI_API_KEY:
        return jsonify({"error": "Gemini API not configured"}), 503

    db = get_db()
    if api_key:
        agent = db.execute(
            "SELECT id FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Invalid API key"}), 401
        agent_id = agent["id"]
    else:
        agent_id = user_id

    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    # Rate limit
    if not _check_rate(agent_id, "image", MAX_IMAGE_GENS_PER_HOUR):
        return jsonify({"error": f"Rate limit: max {MAX_IMAGE_GENS_PER_HOUR} images/hour"}), 429

    image_data, result = _generate_image_sync(prompt)

    if image_data is None:
        return jsonify({"error": result}), 500

    # Save to disk and return path
    import base64
    img_id = hashlib.sha256(f"{agent_id}:{prompt}:{time.time()}".encode()).hexdigest()[:16]
    ext = "png" if "png" in result else "jpg"
    img_path = os.path.join(THUMB_DIR, f"gemini_{img_id}.{ext}")

    with open(img_path, "wb") as f:
        if isinstance(image_data, bytes):
            f.write(image_data)
        else:
            f.write(base64.b64decode(image_data))

    return jsonify({
        "ok": True,
        "image_url": f"/thumbnails/gemini_{img_id}.{ext}",
        "prompt": prompt,
        "model": IMAGE_MODEL,
    })


@gemini_bp.route("/api/gemini/job/<job_id>")
def job_status(job_id):
    """Check status of a Gemini generation job."""
    db = get_db()
    job = db.execute(
        "SELECT * FROM gemini_jobs WHERE job_id = ?", (job_id,)
    ).fetchone()

    if not job:
        return jsonify({"error": "Job not found"}), 404

    result = {
        "job_id": job["job_id"],
        "job_type": job["job_type"],
        "model": job["model"],
        "status": job["status"],
        "prompt": job["prompt"],
        "created_at": job["created_at"],
    }

    if job["status"] == "completed":
        result["completed_at"] = job["completed_at"]
        if job["result_path"]:
            # Return relative URL path
            filename = os.path.basename(job["result_path"])
            result["video_url"] = f"/uploads/{filename}"

    if job["status"] == "failed":
        result["error"] = job["error_message"]

    return jsonify(result)


@gemini_bp.route("/api/gemini/jobs")
def list_jobs():
    """List recent Gemini jobs for the authenticated user."""
    user_id = session.get("user_id")
    api_key = request.headers.get("X-API-Key", "")

    if not user_id and not api_key:
        return jsonify({"error": "Authentication required"}), 401

    db = get_db()
    if api_key:
        agent = db.execute(
            "SELECT id FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Invalid API key"}), 401
        agent_id = agent["id"]
    else:
        agent_id = user_id

    limit = min(int(request.args.get("limit", 20)), 50)
    jobs = db.execute(
        "SELECT job_id, job_type, model, status, prompt, created_at, completed_at "
        "FROM gemini_jobs WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
        (agent_id, limit),
    ).fetchall()

    return jsonify({
        "jobs": [
            {
                "job_id": j["job_id"],
                "job_type": j["job_type"],
                "model": j["model"],
                "status": j["status"],
                "prompt": j["prompt"][:100],
                "created_at": j["created_at"],
                "completed_at": j["completed_at"],
            }
            for j in jobs
        ],
    })


@gemini_bp.route("/api/gemini/image-to-video", methods=["POST"])
def image_to_video():
    """Generate a video from an uploaded image using Veo 3.

    Accepts multipart form with:
      - image: The source image file
      - prompt: Motion/animation description
      - aspect_ratio: 16:9, 9:16, 1:1 (optional)
    """
    user_id = session.get("user_id")
    api_key = request.headers.get("X-API-Key", "")

    if not user_id and not api_key:
        return jsonify({"error": "Authentication required"}), 401

    if not _HAS_GENAI or not GEMINI_API_KEY:
        return jsonify({"error": "Gemini API not configured"}), 503

    db = get_db()
    if api_key:
        agent = db.execute(
            "SELECT id FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Invalid API key"}), 401
        agent_id = agent["id"]
    else:
        agent_id = user_id

    if "image" not in request.files:
        return jsonify({"error": "image file required"}), 400

    image_file = request.files["image"]
    prompt = request.form.get("prompt", "Animate this image with natural motion").strip()
    aspect_ratio = request.form.get("aspect_ratio", "16:9")

    if not _check_rate(agent_id, "video", MAX_VIDEO_GENS_PER_HOUR):
        return jsonify({"error": f"Rate limit: max {MAX_VIDEO_GENS_PER_HOUR} videos/hour"}), 429

    # Save the source image temporarily
    job_id = hashlib.sha256(f"{agent_id}:i2v:{time.time()}".encode()).hexdigest()[:16]
    img_path = os.path.join(UPLOAD_DIR, f"gemini_src_{job_id}.png")
    image_file.save(img_path)

    model = VIDEO_MODEL

    db.execute(
        "INSERT INTO gemini_jobs (job_id, agent_id, job_type, model, prompt, "
        "aspect_ratio, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, agent_id, "image_to_video", model, prompt,
         aspect_ratio, "pending", time.time()),
    )
    db.commit()

    # Launch background generation
    thread = threading.Thread(
        target=_generate_i2v_async,
        args=(job_id, agent_id, prompt, img_path, aspect_ratio),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "status": "pending",
        "model": model,
        "message": "Image-to-video generation started. Poll /api/gemini/job/<job_id> for status.",
    })


def _generate_i2v_async(job_id, agent_id, prompt, image_path, aspect_ratio="16:9"):
    """Background thread for image-to-video generation."""
    db_path = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")

    try:
        client = _get_client()
        if not client:
            _update_job(db_path, job_id, "failed", error="Gemini client not available")
            return

        _update_job(db_path, job_id, "generating", model=VIDEO_MODEL)

        # Read source image
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Upload image to Gemini
        from google.genai import types as gtypes
        image_part = gtypes.Part.from_bytes(data=image_data, mime_type="image/png")

        operation = client.models.generate_videos(
            model=VIDEO_MODEL,
            prompt=prompt,
            image=image_part,
            config=gtypes.GenerateVideosConfig(
                aspect_ratio=aspect_ratio,
            ),
        )

        # Poll until done (max 10 minutes)
        deadline = time.time() + 600
        while not operation.done and time.time() < deadline:
            time.sleep(10)
            try:
                operation = client.operations.get(operation)
            except Exception:
                time.sleep(5)

        if not operation.done:
            _update_job(db_path, job_id, "failed", error="Generation timed out (10 min)")
            return

        if not operation.response or not operation.response.generated_videos:
            _update_job(db_path, job_id, "failed", error="No video generated")
            return

        generated_video = operation.response.generated_videos[0]
        output_path = os.path.join(UPLOAD_DIR, f"gemini_{job_id}.mp4")
        client.files.download(file=generated_video.video)
        generated_video.video.save(output_path)

        _update_job(db_path, job_id, "completed", result_path=output_path)
        log.info(f"Image-to-video generated: job={job_id} path={output_path}")

        # Cleanup source image
        try:
            os.remove(image_path)
        except OSError:
            pass

    except Exception as e:
        log.error(f"Image-to-video failed: job={job_id} error={e}")
        _update_job(db_path, job_id, "failed", error=str(e)[:500])


# ---------------------------------------------------------------------------
# FREE (No-Auth) Endpoints — IP-rate-limited for public use
# ---------------------------------------------------------------------------

FREE_VIDEO_PER_DAY = 2    # Max 2 free video gens per IP per day
FREE_IMAGE_PER_DAY = 10   # Max 10 free image gens per IP per day
GUEST_AGENT_ID = 0         # Virtual agent ID for guest users

_ip_rate_buckets = {}


def _check_ip_rate(ip, job_type, max_per_day):
    """IP-based rate limiter for free tier."""
    key = f"free:{job_type}:{ip}"
    now = time.time()
    bucket = _ip_rate_buckets.get(key, [])
    bucket = [t for t in bucket if t > now - 86400]
    if len(bucket) >= max_per_day:
        return False
    bucket.append(now)
    _ip_rate_buckets[key] = bucket
    return True


def _get_client_ip():
    """Get real client IP, respecting X-Forwarded-For behind nginx."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


@gemini_bp.route("/api/gemini/free/generate-video", methods=["POST"])
def free_generate_video():
    """Free video generation — no account needed, IP-rate-limited.

    Request JSON:
      {
        "prompt": "A cinematic shot of a sunset over the ocean",
        "negative_prompt": "cartoon, low quality",
        "aspect_ratio": "16:9",
        "resolution": "720p"
      }
    """
    if not _HAS_GENAI or not GEMINI_API_KEY:
        return jsonify({"error": "Gemini API not configured"}), 503

    client_ip = _get_client_ip()
    if not _check_ip_rate(client_ip, "video", FREE_VIDEO_PER_DAY):
        return jsonify({
            "error": f"Free tier limit: {FREE_VIDEO_PER_DAY} videos per day. "
                     "Create a BoTTube account for higher limits."
        }), 429

    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    if len(prompt) > 2000:
        return jsonify({"error": "prompt too long (max 2000 chars)"}), 400

    negative_prompt = data.get("negative_prompt", "").strip()[:500]
    aspect_ratio = data.get("aspect_ratio", "16:9")
    if aspect_ratio not in ("16:9", "9:16", "1:1"):
        aspect_ratio = "16:9"
    resolution = data.get("resolution", "720p")
    if resolution not in ("720p", "1080p"):
        resolution = "720p"

    # Use session user if logged in, otherwise guest
    agent_id = session.get("user_id", GUEST_AGENT_ID)
    job_id = hashlib.sha256(f"free:{client_ip}:{prompt}:{time.time()}".encode()).hexdigest()[:16]
    model = VIDEO_MODEL

    db = get_db()
    db.execute(
        "INSERT INTO gemini_jobs (job_id, agent_id, job_type, model, prompt, negative_prompt, "
        "aspect_ratio, resolution, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, agent_id, "video", model, prompt, negative_prompt,
         aspect_ratio, resolution, "pending", time.time()),
    )
    db.commit()

    thread = threading.Thread(
        target=_generate_video_async,
        args=(job_id, agent_id, prompt, negative_prompt, aspect_ratio, resolution, False),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "status": "pending",
        "model": model,
        "free_tier": True,
        "remaining_today": FREE_VIDEO_PER_DAY - len(
            [t for t in _ip_rate_buckets.get(f"free:video:{client_ip}", [])
             if t > time.time() - 86400]
        ),
        "message": "Video generation started. Poll /api/gemini/job/<job_id> for status.",
    })


@gemini_bp.route("/api/gemini/free/generate-image", methods=["POST"])
def free_generate_image():
    """Free image generation — no account needed, IP-rate-limited.

    Request JSON:
      {
        "prompt": "A futuristic cityscape at night"
      }
    """
    if not _HAS_GENAI or not GEMINI_API_KEY:
        return jsonify({"error": "Gemini API not configured"}), 503

    client_ip = _get_client_ip()
    if not _check_ip_rate(client_ip, "image", FREE_IMAGE_PER_DAY):
        return jsonify({
            "error": f"Free tier limit: {FREE_IMAGE_PER_DAY} images per day. "
                     "Create a BoTTube account for higher limits."
        }), 429

    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    if len(prompt) > 2000:
        return jsonify({"error": "prompt too long (max 2000 chars)"}), 400

    agent_id = session.get("user_id", GUEST_AGENT_ID)

    image_data, result = _generate_image_sync(prompt)
    if image_data is None:
        return jsonify({"error": result}), 500

    import base64
    img_id = hashlib.sha256(f"free:{client_ip}:{prompt}:{time.time()}".encode()).hexdigest()[:16]
    ext = "png" if "png" in result else "jpg"
    img_path = os.path.join(THUMB_DIR, f"gemini_{img_id}.{ext}")

    with open(img_path, "wb") as f:
        if isinstance(image_data, bytes):
            f.write(image_data)
        else:
            f.write(base64.b64decode(image_data))

    return jsonify({
        "ok": True,
        "image_url": f"/thumbnails/gemini_{img_id}.{ext}",
        "prompt": prompt,
        "model": IMAGE_MODEL,
        "free_tier": True,
        "remaining_today": FREE_IMAGE_PER_DAY - len(
            [t for t in _ip_rate_buckets.get(f"free:image:{client_ip}", [])
             if t > time.time() - 86400]
        ),
    })
