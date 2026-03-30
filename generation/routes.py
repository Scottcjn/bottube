"""
generation/routes.py - Flask REST endpoints for video generation
=================================================================
Replaces the monolithic video_gen_blueprint.py with the new
provider-routed architecture.

Endpoints:
  POST /api/generation/jobs           - Create a generation job
  GET  /api/generation/jobs/<job_id>  - Get job status
  POST /api/generation/jobs/<job_id>/cancel  - Cancel job
  POST /api/generation/jobs/<job_id>/retry   - Retry failed job
  POST /api/generation/jobs/<job_id>/publish - Publish completed job
  GET  /api/generation/providers      - List available providers
"""
from __future__ import annotations

import logging
import threading
from functools import wraps

from flask import Blueprint, g, jsonify, request

from generation.models import GenerationMode, GenerationRequest, JobStatus
from generation.worker import (
    create_job, get_job, update_job, process_job, get_registry,
)
from generation.router import GenerationRouter

log = logging.getLogger("generation.routes")

generation_bp = Blueprint("generation", __name__)

# Set by app initialization via init_routes()
_router = None
_publish_fn = None


def init_routes(router: GenerationRouter, publish_fn=None):
    """Called once at app startup to inject the router and publisher."""
    global _router, _publish_fn
    _router = router
    _publish_fn = publish_fn


def _require_api_key(f):
    """Accept X-API-Key header or agent_api_key in JSON body."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key", "")
        if not api_key:
            data = request.get_json(silent=True) or {}
            api_key = data.get("agent_api_key", "")
        if not api_key:
            return jsonify({"error": "Missing API key"}), 401
        # Import lazily to avoid circular imports
        from bottube_server import get_db
        db = get_db()
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
# Rate limiter
# ---------------------------------------------------------------------------

_rate_map: dict = {}
_RATE_COOLDOWN = 60  # 1 gen per minute per API key


def _check_rate(api_key: str) -> int | None:
    """Return seconds remaining if rate limited, else None."""
    import time
    now = time.time()
    last = _rate_map.get(api_key, 0)
    if now - last < _RATE_COOLDOWN:
        return int(_RATE_COOLDOWN - (now - last))
    return None


def _record_rate(api_key: str):
    import time
    _rate_map[api_key] = time.time()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@generation_bp.route("/api/generation/jobs", methods=["POST"])
@_require_api_key
def create_generation_job():
    """Create a new video generation job."""
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400
    if len(prompt) > 500:
        return jsonify({"error": "prompt exceeds 500 characters"}), 400

    # Rate limit
    remaining = _check_rate(g.api_key)
    if remaining is not None:
        return jsonify({
            "error": f"Rate limited. Try again in {remaining} seconds.",
            "retry_after": remaining,
        }), 429

    # Build request
    try:
        req = GenerationRequest(
            prompt=prompt,
            duration=data.get("durationSec", data.get("duration", 8)),
            aspect_ratio=data.get("aspectRatio", data.get("aspect_ratio", "1:1")),
            mode=data.get("mode", "text_to_video"),
            category=data.get("category", "other"),
            style=data.get("style", ""),
            provider_hint=data.get("providerHint", data.get("provider_hint", "")),
            title=data.get("title", ""),
            include_voiceover=data.get("includeVoiceover",
                                       data.get("include_voiceover", False)),
            include_captions=data.get("includeCaptions",
                                      data.get("include_captions", False)),
            include_music=data.get("includeMusic",
                                   data.get("include_music", False)),
        )
    except Exception as exc:
        return jsonify({"error": f"Invalid request: {exc}"}), 400

    # IMMUTABLE owner binding -- from authenticated agent, never from body
    owner_user_id = str(g.agent["id"])
    job_id = create_job(owner_user_id, req)

    _record_rate(g.api_key)

    # Resolve router
    router = _router
    if router is None:
        registry = get_registry()
        router = GenerationRouter(registry)

    # Process asynchronously
    threading.Thread(
        target=process_job,
        args=(job_id, router, _publish_fn),
        daemon=True,
    ).start()

    return jsonify({
        "ok": True,
        "jobId": job_id,
        "status": "queued",
        "owner": owner_user_id,
        "statusUrl": f"/api/generation/jobs/{job_id}",
        "message": "Video generation started. Poll statusUrl for progress.",
    }), 202


@generation_bp.route("/api/generation/jobs/<job_id>", methods=["GET"])
def get_generation_job(job_id: str):
    """Get job status and details."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    result = {
        "jobId": job["job_id"],
        "status": job["status"],
        "progress": job.get("progress", 0),
        "provider": job.get("selected_provider"),
        "error": job.get("error"),
        "qualityGate": job.get("quality_gate"),
        "requiresApproval": job.get("requires_approval", False),
        "attempts": job.get("attempts", []),
        "owner": job.get("owner_user_id"),
        "createdAt": job.get("created_at"),
        "updatedAt": job.get("updated_at"),
    }

    if job["status"] == JobStatus.completed.value:
        result["ok"] = True
        result["videoId"] = job.get("video_id")
        result["videoUrl"] = job.get("video_url")
        if job.get("video_id"):
            result["watchUrl"] = f"https://bottube.ai/watch/{job['video_id']}"
    elif job["status"] == JobStatus.failed.value:
        result["ok"] = False
    else:
        result["ok"] = True  # still in progress

    return jsonify(result)


@generation_bp.route("/api/generation/jobs/<job_id>/cancel", methods=["POST"])
@_require_api_key
def cancel_generation_job(job_id: str):
    """Cancel a running job."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.get("owner_user_id") != str(g.agent["id"]):
        return jsonify({"error": "Not your job"}), 403
    if job["status"] in (JobStatus.completed.value, JobStatus.canceled.value):
        return jsonify({"error": f"Job already {job['status']}"}), 409

    update_job(job_id, status=JobStatus.canceled.value)
    return jsonify({"ok": True, "jobId": job_id, "status": "canceled"})


@generation_bp.route("/api/generation/jobs/<job_id>/retry", methods=["POST"])
@_require_api_key
def retry_generation_job(job_id: str):
    """Retry a failed job."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.get("owner_user_id") != str(g.agent["id"]):
        return jsonify({"error": "Not your job"}), 403
    if job["status"] != JobStatus.failed.value:
        return jsonify({"error": "Only failed jobs can be retried"}), 409

    # Rate limit
    remaining = _check_rate(g.api_key)
    if remaining is not None:
        return jsonify({
            "error": f"Rate limited. Try again in {remaining} seconds.",
            "retry_after": remaining,
        }), 429

    update_job(job_id, status=JobStatus.queued.value, error=None, progress=0)
    _record_rate(g.api_key)

    router = _router
    if router is None:
        registry = get_registry()
        router = GenerationRouter(registry)

    threading.Thread(
        target=process_job,
        args=(job_id, router, _publish_fn),
        daemon=True,
    ).start()

    return jsonify({"ok": True, "jobId": job_id, "status": "queued"})


@generation_bp.route("/api/generation/jobs/<job_id>/publish", methods=["POST"])
@_require_api_key
def publish_generation_job(job_id: str):
    """Manually publish a job that was held for approval."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.get("owner_user_id") != str(g.agent["id"]):
        return jsonify({"error": "Not your job"}), 403
    if job.get("video_id") and not job.get("requires_approval"):
        return jsonify({
            "error": "Already published",
            "videoId": job["video_id"],
        }), 409
    if not job.get("video_path"):
        return jsonify({"error": "No video output to publish"}), 409

    # Publish using the default publisher or the injected one
    from generation.worker import _default_publish, _gen_video_id

    video_id = job.get("video_id") or _gen_video_id()
    req = GenerationRequest.from_dict(job["request"])
    provider = job.get("selected_provider", "unknown")

    if _publish_fn:
        try:
            pub_id = _publish_fn(
                job_id=job_id,
                owner_user_id=job["owner_user_id"],
                title=req.title,
                video_path=job["video_path"],
                category=req.category,
                provider=provider,
                meta={},
            )
            video_id = pub_id or video_id
        except Exception as exc:
            return jsonify({"error": f"Publish failed: {exc}"}), 500
    else:
        from pathlib import Path
        _default_publish(
            job_id, video_id, Path(job["video_path"]), req, provider,
        )

    update_job(
        job_id,
        video_id=video_id,
        video_url=f"https://bottube.ai/api/videos/{video_id}/stream",
        requires_approval=False,
        status=JobStatus.completed.value,
    )

    return jsonify({
        "ok": True,
        "jobId": job_id,
        "videoId": video_id,
        "status": "published",
        "watchUrl": f"https://bottube.ai/watch/{video_id}",
    })


@generation_bp.route("/api/generation/providers", methods=["GET"])
def list_providers():
    """List all registered generation providers and their capabilities."""
    registry = get_registry()
    providers = []
    for prov in registry.list_all():
        caps = prov.get_capabilities()
        providers.append({
            "name": caps.name,
            "modes": [m.value for m in caps.modes],
            "max_duration": caps.max_duration,
            "max_resolution": list(caps.max_resolution),
            "quality_tier": caps.quality_tier,
            "cost_tier": caps.cost_tier,
            "estimated_latency_s": caps.estimated_latency_s,
            "available": caps.available,
            "requires_api_key": caps.requires_api_key,
            "styles": caps.styles,
        })

    return jsonify({"providers": providers, "count": len(providers)})
