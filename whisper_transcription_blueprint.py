"""
BoTTube Whisper Transcription Blueprint (Bounty #750)

Exposes REST API endpoints for:
- GET  /api/videos/<video_id>/transcript          → JSON transcript info
- GET  /api/videos/<video_id>/transcript/text     → plain text download
- GET  /api/videos/<video_id>/transcript/srt      → SRT subtitle file
- GET  /api/videos/<video_id>/transcript/vtt      → WebVTT subtitle file
- POST /api/videos/<video_id>/transcript/trigger  → manually trigger transcription
- GET  /api/transcript/search?q=...               → FTS search across transcripts
- POST /api/transcript/backfill                   → backfill existing videos (admin)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, Response

import whisper_transcription as wt

log = logging.getLogger("bottube.whisper_transcription_blueprint")

whisper_bp = Blueprint("whisper_transcription", __name__)


def _video_dir() -> str:
    return os.environ.get(
        "BOTTUBE_VIDEO_DIR",
        str(Path(wt._get_db_path()).parent / "videos"),
    )


def _video_path(filename: str) -> str:
    return str(Path(_video_dir()) / filename)


def _get_video_filename(video_id: str) -> str | None:
    """Look up the filename for a video_id from the database."""
    try:
        with wt._connect_db() as db:
            row = db.execute(
                "SELECT filename FROM videos WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            return row["filename"] if row else None
    except Exception as exc:
        log.error("DB lookup failed for %s: %s", video_id, exc)
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@whisper_bp.route("/api/videos/<video_id>/transcript")
def get_transcript(video_id: str):
    """Return transcript metadata and text for a video."""
    data = wt.get_transcript(video_id)
    if data is None:
        return jsonify({"error": "Transcript not found", "video_id": video_id}), 404
    # Don't send full SRT/VTT in the JSON overview — use dedicated endpoints
    return jsonify({
        "video_id": data["video_id"],
        "language": data["language"],
        "language_probability": data["language_prob"],
        "plain_text": data["plain_text"],
        "model": data["model"],
        "source": data["source"],
        "duration_sec": data["duration_sec"],
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
        "has_srt": bool(data["srt_data"]),
        "has_vtt": bool(data["vtt_data"]),
    })


@whisper_bp.route("/api/videos/<video_id>/transcript/text")
def get_transcript_text(video_id: str):
    """Serve plain-text transcript."""
    data = wt.get_transcript(video_id)
    if data is None:
        return Response("Transcript not found", status=404, mimetype="text/plain")
    return Response(
        data["plain_text"],
        mimetype="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{video_id}.txt"',
            "Cache-Control": "public, max-age=86400",
        },
    )


@whisper_bp.route("/api/videos/<video_id>/transcript/srt")
def get_transcript_srt(video_id: str):
    """Serve SRT subtitle file."""
    data = wt.get_transcript(video_id)
    if data is None:
        return Response("Transcript not found", status=404, mimetype="text/plain")
    return Response(
        data["srt_data"],
        mimetype="text/srt",
        headers={
            "Content-Disposition": f'attachment; filename="{video_id}.srt"',
            "Cache-Control": "public, max-age=86400",
        },
    )


@whisper_bp.route("/api/videos/<video_id>/transcript/vtt")
def get_transcript_vtt(video_id: str):
    """Serve WebVTT subtitle file."""
    data = wt.get_transcript(video_id)
    if data is None:
        return Response("Transcript not found", status=404, mimetype="text/plain")
    return Response(
        data["vtt_data"],
        mimetype="text/vtt",
        headers={
            "Content-Disposition": f'attachment; filename="{video_id}.vtt"',
            "Cache-Control": "public, max-age=86400",
        },
    )


@whisper_bp.route("/api/videos/<video_id>/transcript/trigger", methods=["POST"])
def trigger_transcription(video_id: str):
    """Manually trigger transcription for a video.

    Body (JSON, optional):
        { "force": true }   — re-transcribe even if transcript already exists
    """
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force", False))

    filename = _get_video_filename(video_id)
    if filename is None:
        return jsonify({"error": "Video not found", "video_id": video_id}), 404

    video_path = _video_path(filename)
    wt.enqueue_transcription(video_id, video_path, force=force)

    return jsonify({
        "status": "queued",
        "video_id": video_id,
        "force": force,
    }), 202


@whisper_bp.route("/api/transcript/search")
def search_transcripts():
    """Search transcripts with full-text search."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    limit = request.args.get("limit", 50, type=int)
    video_ids = wt.search_transcripts(query, limit=limit)
    return jsonify({
        "query": query,
        "count": len(video_ids),
        "video_ids": video_ids,
    })


@whisper_bp.route("/api/transcript/backfill", methods=["POST"])
def trigger_backfill():
    """Backfill transcriptions for all existing videos (admin endpoint).

    Body (JSON, optional):
        { "force": false, "batch_size": 50 }
    """
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force", False))
    batch_size = int(body.get("batch_size", 50))
    enqueued = wt.backfill_existing_videos(
        video_dir=_video_dir(),
        force=force,
        batch_size=batch_size,
    )
    return jsonify({
        "status": "backfill_queued",
        "enqueued": enqueued,
        "force": force,
    })
