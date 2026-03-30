"""
generation/worker.py - Background job processor
=================================================
Processes queued generation jobs through the pipeline:
  route -> submit -> poll -> retrieve -> quality gate -> publish

Runs in a background thread started by the Flask app.
Falls back through the provider chain on failure.

Exports used by routes.py:
  create_job, get_job, update_job, process_job, get_registry
"""
from __future__ import annotations

import json
import logging
import os
import random
import shutil
import sqlite3
import string
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, Optional

from generation.models import GenerationRequest, JobStatus
from generation.quality_gate import check_quality, QualityGateResult
from generation.router import GenerationRouter
from generation.provider import ProviderRegistry

log = logging.getLogger("generation.worker")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_BASE_DIR = Path(os.environ.get(
    "BOTTUBE_BASE_DIR",
    str(Path(__file__).resolve().parent.parent),
))
_VIDEO_DIR = _BASE_DIR / "videos"
_THUMB_DIR = _BASE_DIR / "thumbnails"
_GEN_WORK_DIR = _BASE_DIR / "generation_work"
_DB_PATH = _BASE_DIR / "bottube.db"

for _d in (_VIDEO_DIR, _THUMB_DIR, _GEN_WORK_DIR):
    _d.mkdir(parents=True, exist_ok=True)

_POLL_INTERVAL = 3        # seconds between async polls
_POLL_TIMEOUT = 300       # 5 minutes max wait per provider

# ---------------------------------------------------------------------------
# In-memory job store (small -- jobs expire after 2 hours)
# ---------------------------------------------------------------------------

_jobs: Dict[str, dict] = {}
_jobs_lock = threading.Lock()
_JOBS_TTL = 7200


def _prune_jobs():
    now = time.time()
    expired = [jid for jid, j in _jobs.items()
               if now - j.get("created_at", 0) > _JOBS_TTL]
    for jid in expired:
        _jobs.pop(jid, None)


def create_job(owner_user_id: str, request: GenerationRequest) -> str:
    """Create a new generation job.  owner_user_id is IMMUTABLE."""
    job_id = uuid.uuid4().hex[:16]
    now = time.time()
    with _jobs_lock:
        _prune_jobs()
        _jobs[job_id] = {
            "job_id": job_id,
            "owner_user_id": str(owner_user_id),   # IMMUTABLE -- never changed
            "request": request.to_dict(),
            "status": JobStatus.queued.value,
            "selected_provider": None,
            "fallback_chain": [],
            "external_id": None,
            "progress": 0,
            "error": None,
            "video_path": None,
            "video_id": None,
            "video_url": None,
            "quality_gate": None,
            "requires_approval": False,
            "attempts": [],
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    with _jobs_lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


def update_job(job_id: str, **kwargs):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)
            _jobs[job_id]["updated_at"] = time.time()


# ---------------------------------------------------------------------------
# Provider registry (singleton)
# ---------------------------------------------------------------------------

_registry: Optional[ProviderRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> ProviderRegistry:
    """Lazily create and return the singleton ProviderRegistry."""
    global _registry
    if _registry is not None:
        return _registry

    with _registry_lock:
        if _registry is not None:
            return _registry

        reg = ProviderRegistry()

        from generation.providers.comfyui_ltx import ComfyUILTXProvider
        from generation.providers.huggingface import HuggingFaceProvider
        from generation.providers.gemini import GeminiProvider
        from generation.providers.stability import StabilityProvider
        from generation.providers.fal_ai import FalAIProvider
        from generation.providers.replicate import ReplicateProvider
        from generation.providers.ffmpeg_titlecard import FFmpegTitleCardProvider

        reg.register(ComfyUILTXProvider())
        reg.register(HuggingFaceProvider())
        reg.register(GeminiProvider())
        reg.register(StabilityProvider())
        reg.register(FalAIProvider())
        reg.register(ReplicateProvider())
        reg.register(FFmpegTitleCardProvider())

        _registry = reg
        log.info("Provider registry initialized with %d providers", len(reg.names()))
        return _registry


# ---------------------------------------------------------------------------
# Video ID generation (matches existing BoTTube format)
# ---------------------------------------------------------------------------

def _gen_video_id(length: int = 11) -> str:
    chars = string.ascii_letters + string.digits + "-_"
    return "".join(random.choice(chars) for _ in range(length))


# ---------------------------------------------------------------------------
# Main processing function
# ---------------------------------------------------------------------------

def process_job(job_id: str, router: GenerationRouter, publish_fn=None):
    """Process a single job through the full pipeline.

    Called by routes.py in a background thread.
    """
    job = get_job(job_id)
    if not job:
        log.error("Job %s not found", job_id)
        return

    req = GenerationRequest.from_dict(job["request"])

    # Work directory for this job
    work_dir = _GEN_WORK_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        _run_pipeline(job_id, req, router, publish_fn, work_dir)
    except Exception as exc:
        log.error("Job %s pipeline error: %s", job_id, exc, exc_info=True)
        update_job(job_id, status=JobStatus.failed.value, error=str(exc)[:500])
    finally:
        _cleanup_work_dir(work_dir)


def _run_pipeline(
    job_id: str,
    req: GenerationRequest,
    router: GenerationRouter,
    publish_fn,
    work_dir: Path,
):
    """Route -> submit -> poll -> quality gate -> publish."""

    # --- Step 1: Route ---
    update_job(job_id, status=JobStatus.routing.value)
    try:
        decision = router.route(req)
        providers_to_try = [decision.provider] + decision.fallback_chain
        update_job(
            job_id,
            selected_provider=decision.provider,
            fallback_chain=decision.fallback_chain,
        )
        log.info("Job %s routed to %s (fallbacks: %s)",
                 job_id, decision.provider, decision.fallback_chain)
    except Exception as exc:
        update_job(job_id, status=JobStatus.failed.value,
                   error=f"Routing failed: {exc}")
        return

    # --- Step 2: Try providers in chain ---
    for attempt_num, provider_name in enumerate(providers_to_try):
        provider = router.registry.get(provider_name)
        if not provider:
            log.warning("Provider %s not found, skipping", provider_name)
            continue

        update_job(
            job_id,
            status=JobStatus.submitted.value,
            selected_provider=provider_name,
            progress=10,
        )

        # Validate
        ok, reason = provider.validate_input(req)
        if not ok:
            log.warning("Provider %s rejected input: %s", provider_name, reason)
            _record_attempt(job_id, provider_name, attempt_num, False, reason)
            continue

        # Submit
        update_job(job_id, status=JobStatus.generating.value, progress=30)
        try:
            success, external_id = provider.submit(req, work_dir)
        except Exception as exc:
            log.error("Provider %s submit error: %s", provider_name, exc)
            _record_attempt(job_id, provider_name, attempt_num, False, str(exc))
            continue

        if not success:
            log.warning("Provider %s failed: %s", provider_name, external_id)
            _record_attempt(job_id, provider_name, attempt_num, False, external_id)
            continue

        # Determine result path
        result_path = None

        # For synchronous providers, external_id is a local file path
        if external_id and Path(external_id).exists():
            result_path = Path(external_id)
        else:
            # Async provider -- poll until complete
            result_path = _poll_provider(job_id, provider, external_id, work_dir)

        if not result_path or not result_path.exists():
            _record_attempt(job_id, provider_name, attempt_num, False, "no output file")
            continue

        _record_attempt(job_id, provider_name, attempt_num, True, "ok")
        update_job(job_id, progress=70)

        # --- Step 3: Transcode ---
        update_job(job_id, status=JobStatus.transcoding.value, progress=75)
        video_id = _gen_video_id()
        final_path = _VIDEO_DIR / f"{video_id}.mp4"

        if not _transcode_to_mp4(result_path, final_path):
            # If transcode fails but source is already mp4, try direct copy
            if result_path.suffix == ".mp4":
                shutil.copy2(result_path, final_path)
            else:
                log.warning("Transcode failed for provider %s", provider_name)
                final_path.unlink(missing_ok=True)
                _record_attempt(job_id, provider_name, attempt_num, False, "transcode failed")
                continue

        update_job(job_id, video_path=str(final_path), video_id=video_id)

        # --- Step 4: Quality gate ---
        update_job(job_id, status=JobStatus.assembling.value, progress=80)
        caps = provider.get_capabilities()
        gate_result = check_quality(
            str(final_path),
            provider_name,
            {"quality_tier": caps.quality_tier},
        )
        update_job(job_id, quality_gate=gate_result.to_dict())

        if not gate_result.passed and not gate_result.requires_approval:
            log.warning("Quality gate failed for %s: %s", provider_name, gate_result.reason)
            final_path.unlink(missing_ok=True)
            continue  # try next provider

        # --- Step 5: Publish ---
        if gate_result.requires_approval:
            # Hold for manual approval -- do not auto-publish
            update_job(
                job_id,
                status=JobStatus.completed.value,
                requires_approval=True,
                video_url=f"https://bottube.ai/api/videos/{video_id}/stream",
                progress=100,
            )
            log.info("Job %s completed but requires approval (score=%d, reason=%s)",
                     job_id, gate_result.score, gate_result.reason)
            return

        if gate_result.passed:
            update_job(job_id, status=JobStatus.publishing.value, progress=90)
            if publish_fn:
                try:
                    pub_video_id = publish_fn(
                        job_id=job_id,
                        owner_user_id=get_job(job_id)["owner_user_id"],
                        title=req.title,
                        video_path=str(final_path),
                        category=req.category,
                        provider=provider_name,
                        meta={"quality_tier": caps.quality_tier},
                    )
                    update_job(
                        job_id,
                        status=JobStatus.completed.value,
                        video_id=pub_video_id or video_id,
                        video_url=f"https://bottube.ai/api/videos/{pub_video_id or video_id}/stream",
                        progress=100,
                        completed_at=time.time(),
                    )
                    log.info("Job %s published as video %s via publish_fn",
                             job_id, pub_video_id or video_id)
                    return
                except Exception as exc:
                    log.error("Publish failed: %s", exc)
                    update_job(job_id, status=JobStatus.failed.value,
                               error=f"Publish: {exc}")
                    return
            else:
                # Default publish: insert into BoTTube DB
                _default_publish(job_id, video_id, final_path, req, provider_name)
                update_job(
                    job_id,
                    status=JobStatus.completed.value,
                    video_url=f"https://bottube.ai/api/videos/{video_id}/stream",
                    progress=100,
                    completed_at=time.time(),
                )
                log.info("Job %s published as video %s (default publisher)",
                         job_id, video_id)
                return

    # All providers exhausted
    update_job(
        job_id,
        status=JobStatus.failed.value,
        error="All providers failed -- see attempts",
    )
    log.error("Job %s: all providers exhausted", job_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record_attempt(job_id: str, provider: str, attempt: int,
                    success: bool, detail: str):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].setdefault("attempts", []).append({
                "provider": provider,
                "attempt": attempt,
                "success": success,
                "detail": detail[:500],
                "timestamp": time.time(),
            })


def _poll_provider(job_id, provider, external_id, work_dir) -> Optional[Path]:
    """Poll an async provider until complete or timeout."""
    deadline = time.time() + _POLL_TIMEOUT
    while time.time() < deadline:
        # Check if job was canceled
        job = get_job(job_id)
        if job and job["status"] == JobStatus.canceled.value:
            provider.cancel(external_id)
            return None

        status_str, progress = provider.get_status(external_id)
        update_job(job_id, progress=int(30 + progress * 40))

        if status_str == "completed":
            result_path = provider.get_result(external_id, work_dir)
            if result_path and result_path.exists():
                return result_path
            return None
        elif status_str == "failed":
            return None

        time.sleep(_POLL_INTERVAL)

    # Timeout
    provider.cancel(external_id)
    return None


def _transcode_to_mp4(input_path: Path, output_path: Path) -> bool:
    """Transcode any video/webp to standard 720x720 MP4 with silent audio."""
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", (
            "scale=720:720:force_original_aspect_ratio=decrease,"
            "pad=720:720:(ow-iw)/2:(oh-ih)/2:color=0x1a1a2e"
        ),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-c:a", "aac", "-shortest",
        str(output_path),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=120, check=False,
        )
        return result.returncode == 0 and output_path.exists()
    except Exception:
        return False


def _default_publish(
    job_id: str,
    video_id: str,
    final_path: Path,
    req: GenerationRequest,
    provider: str,
):
    """Insert video record into the BoTTube SQLite database."""
    job = get_job(job_id)
    if not job:
        return

    owner_user_id = job["owner_user_id"]

    # Generate thumbnail
    thumb_filename = f"{video_id}.jpg"
    thumb_path = _THUMB_DIR / thumb_filename
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(final_path),
                "-vf", "thumbnail,scale=320:320",
                "-frames:v", "1",
                str(thumb_path),
            ],
            capture_output=True, timeout=15, check=False,
        )
        if not thumb_path.exists():
            thumb_filename = ""
    except Exception:
        thumb_filename = ""

    # Get video metadata
    duration = 0.0
    width, height = 720, 720
    try:
        probe_result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-show_entries", "stream=width,height",
                "-of", "json", str(final_path),
            ],
            capture_output=True, text=True, timeout=10, check=False,
        )
        probe_data = json.loads(probe_result.stdout)
        duration = float(probe_data.get("format", {}).get("duration", 0))
        for stream in probe_data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = int(stream.get("width", 720))
                height = int(stream.get("height", 720))
                break
    except Exception:
        pass

    # Vision screening
    screening_status = "pending_review"
    screening_details = "{}"
    try:
        from vision_screener import screen_video as vs_screen
        sr = vs_screen(str(final_path), run_tier2=True)
        screening_status = sr.get("status", "pending_review")
        screening_details = json.dumps(sr)
    except ImportError:
        pass

    # Insert into DB
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")

        agent_id = int(owner_user_id)

        # Use the generation-aware insert with source columns
        conn.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, description, filename, thumbnail,
                duration_sec, width, height, tags, scene_description, category,
                novelty_score, novelty_flags, revision_of, revision_note,
                challenge_id, created_at,
                screening_status, screening_details,
                is_removed, removed_reason,
                source_job_id, source_provider, source_model)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id, agent_id,
                req.title, req.prompt,
                f"{video_id}.mp4", thumb_filename,
                duration, width, height,
                json.dumps([]),   # tags
                req.prompt,       # scene_description
                req.category,
                0.0, "",          # novelty_score, novelty_flags
                "", "",           # revision_of, revision_note
                "",               # challenge_id
                time.time(),
                screening_status, screening_details,
                1 if screening_status == "failed" else 0,
                "",
                # Generation metadata columns
                job_id,
                provider or "",
                "",               # source_model (provider-specific)
            ),
        )
        conn.commit()
        conn.close()
        log.info("Video %s inserted into DB (agent=%s, provider=%s)",
                 video_id, agent_id, provider)
    except Exception as exc:
        log.error("Failed to insert video record: %s", exc)


def _cleanup_work_dir(work_dir: Path):
    """Remove temporary work directory."""
    try:
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# GenerationWorker class (optional background loop for polling)
# ---------------------------------------------------------------------------

class GenerationWorker:
    """Background thread that processes queued jobs automatically."""

    def __init__(self, router: GenerationRouter, publish_fn=None,
                 poll_interval: float = 2.0):
        self.router = router
        self.publish_fn = publish_fn
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Generation worker started (poll=%.1fs)", self.poll_interval)

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._process_queued()
            except Exception as exc:
                log.error("Worker loop error: %s", exc)
            time.sleep(self.poll_interval)

    def _process_queued(self):
        with _jobs_lock:
            queued = [jid for jid, j in _jobs.items()
                      if j.get("status") == JobStatus.queued.value]
        for job_id in queued:
            try:
                process_job(job_id, self.router, self.publish_fn)
            except Exception as exc:
                log.error("Failed processing job %s: %s", job_id, exc)
                update_job(job_id, status=JobStatus.failed.value, error=str(exc))
