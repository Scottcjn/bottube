"""
BoTTube Auto-Captions via OpenAI Whisper

Generates WebVTT and SRT captions for videos. Stores in DB and serves via API.
Adds full-text search for captions.

Milestones:
- Whisper transcription pipeline (upload → transcript) - 20 RTC
- Searchable transcripts in BoTTube search - +5 RTC
- SRT/VTT subtitle file generation - +5 RTC

Usage:
    from whisper_blueprint import whisper_bp, init_whisper_tables, generate_whisper_captions_for_video
    init_whisper_tables()
    app.register_blueprint(whisper_bp)
"""

import io
import json
import logging
import os
import sqlite3
import subprocess
import tempfile
import threading
import time

from flask import Blueprint, current_app, g, jsonify, request

log = logging.getLogger("bottube.whisper")

whisper_bp = Blueprint("whisper", __name__)

# Whisper config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
WHISPER_API_URL = "https://api.openai.com/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-1"

DB_PATH = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")


def _get_db():
    """Get database connection."""
    try:
        from bottube_server import get_db
        return get_db()
    except Exception:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        return db


def init_whisper_tables():
    """Create/upgrade captions tables for Whisper support."""
    db = sqlite3.connect(DB_PATH)

    # Create captions table if not exists
    db.execute("""
        CREATE TABLE IF NOT EXISTS video_captions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            language TEXT DEFAULT 'en',
            format TEXT DEFAULT 'vtt',
            caption_data TEXT NOT NULL,
            source TEXT DEFAULT 'auto',
            created_at REAL NOT NULL,
            UNIQUE(video_id, language)
        )
    """)

    # Add full-text search support
    try:
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS video_captions_fts USING fts5(video_id, caption_data)")
        log.info("Full-text search enabled for captions")
    except Exception as e:
        log.warning(f"FTS table creation failed (may already exist): {e}")

    db.commit()
    db.close()
    log.info("Whisper captions tables initialized")


def _extract_audio(video_path: str) -> str:
    """Extract audio from video file as 16kHz mono WAV using ffmpeg."""
    audio_path = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", "-y", audio_path],
            capture_output=True, timeout=120, check=True
        )
        return audio_path
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.error(f"Audio extraction failed: {e}")
        return ""


def _speech_to_text(audio_path: str) -> dict:
    """Transcribe audio using OpenAI Whisper API."""
    if not OPENAI_API_KEY:
        log.error("OPENAI_API_KEY not configured")
        return {}

    try:
        with open(audio_path, "rb") as audio_file:
            response = subprocess.run(
                ["curl", "-s", "-X", "POST", WHISPER_API_URL,
                 "-H", f"Authorization: Bearer {OPENAI_API_KEY}",
                 "-H", "Content-Type: multipart/form-data",
                 "-F", f"file=@{audio_path}",
                 "-F", f"model={WHISPER_MODEL}",
                 "-F", "response_format=verbose_json"],
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes max
            )

            if response.returncode != 0:
                log.error(f"Whisper API failed: {response.stderr}")
                return {}

            result = json.loads(response.stdout)
            log.info(f"Whisper transcription successful: {len(result.get('segments', []))} segments")
            return result

    except Exception as e:
        log.error(f"Speech-to-text failed: {e}")
        return {}


def _words_to_vtt(segments: list) -> str:
    """Convert Whisper segments to WebVTT format."""
    if not segments:
        return ""

    lines = ["WEBVTT", ""]
    cue_num = 1

    for segment in segments:
        start = segment.get("start", 0)
        end = segment.get("end", 0)
        text = segment.get("text", "").strip()

        if text:
            lines.append(str(cue_num))
            lines.append(f"{_format_vtt_time(start)} --> {_format_vtt_time(end)}")
            lines.append(text)
            lines.append("")
            cue_num += 1

    return "\n".join(lines)


def _words_to_srt(segments: list) -> str:
    """Convert Whisper segments to SRT format."""
    if not segments:
        return ""

    lines = []
    cue_num = 1

    for segment in segments:
        start = segment.get("start", 0)
        end = segment.get("end", 0)
        text = segment.get("text", "").strip()

        if text:
            lines.append(str(cue_num))
            lines.append(_format_srt_time(start) + " --> " + _format_srt_time(end))
            lines.append(text)
            lines.append("")
            cue_num += 1

    return "\n".join(lines)


def _format_vtt_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for WebVTT."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _format_srt_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS,mmm for SRT."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_whisper_captions_for_video(video_id: str, video_path: str) -> bool:
    """Generate captions for a video using Whisper and store in DB. Returns True on success."""
    log.info(f"Generating Whisper captions for {video_id}")

    # Extract audio
    audio_path = _extract_audio(video_path)
    if not audio_path:
        return False

    try:
        # Send to Whisper
        result = _speech_to_text(audio_path)
        segments = result.get("segments", [])
        text = result.get("text", "")

        if not segments:
            log.warning(f"No speech detected in {video_id}")
            return False

        # Generate both formats
        vtt = _words_to_vtt(segments)
        srt = _words_to_srt(segments)

        if not vtt or not srt:
            return False

        # Store in database
        db = sqlite3.connect(DB_PATH)
        now = time.time()

        # Store WebVTT
        db.execute(
            "INSERT OR REPLACE INTO video_captions (video_id, language, format, caption_data, source, created_at) "
            "VALUES (?, 'en', 'vtt', ?, 'whisper', ?)",
            (video_id, vtt, now),
        )

        # Store SRT
        db.execute(
            "INSERT OR REPLACE INTO video_captions (video_id, language, format, caption_data, source, created_at) "
            "VALUES (?, 'en', 'srt', ?, 'whisper', ?)",
            (video_id, srt, now),
        )

        # Update full-text search index
        db.execute(
            "INSERT OR REPLACE INTO video_captions_fts (video_id, caption_data) "
            "VALUES (?, ?)",
            (video_id, text),
        )

        db.commit()
        db.close()
        log.info(f"Whisper captions generated for {video_id}: {len(segments)} segments")
        return True
    finally:
        try:
            os.unlink(audio_path)
        except OSError:
            pass


def generate_whisper_captions_async(video_id: str, video_path: str):
    """Fire-and-forget Whisper caption generation in background thread."""
    if not OPENAI_API_KEY:
        log.warning("OPENAI_API_KEY not configured, skipping Whisper captions")
        return

    t = threading.Thread(
        target=generate_whisper_captions_for_video,
        args=(video_id, video_path),
        daemon=True,
    )
    t.start()


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@whisper_bp.route("/api/videos/<video_id>/captions")
def get_captions(video_id):
    """Serve WebVTT or SRT captions for a video."""
    lang = request.args.get("lang", "en")
    fmt = request.args.get("format", "vtt").lower()

    db = _get_db()
    row = db.execute(
        "SELECT caption_data FROM video_captions WHERE video_id = ? AND language = ? AND format = ?",
        (video_id, lang, fmt),
    ).fetchone()

    if not row:
        return jsonify({"error": "Captions not found"}), 404

    # Set content type based on format
    if fmt == "srt":
        mimetype = "text/srt"
    else:
        mimetype = "text/vtt"

    return current_app.response_class(
        row["caption_data"],
        mimetype=mimetype,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@whisper_bp.route("/api/videos/<video_id>/captions/status")
def caption_status(video_id):
    """Check if captions exist for a video."""
    db = _get_db()
    rows = db.execute(
        "SELECT language, source, format, created_at FROM video_captions WHERE video_id = ?",
        (video_id,),
    ).fetchall()

    return jsonify({
        "video_id": video_id,
        "captions": [
            {"language": r["language"], "source": r["source"], "format": r["format"], "created_at": r["created_at"]}
            for r in rows
        ],
    })


@whisper_bp.route("/api/search/captions")
def search_captions():
    """Search video captions by text content (full-text search)."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    db = _get_db()
    try:
        results = db.execute(
            "SELECT DISTINCT video_id FROM video_captions_fts WHERE caption_data MATCH ?",
            (query,),
        ).fetchall()

        return jsonify({
            "query": query,
            "count": len(results),
            "video_ids": [r["video_id"] for r in results],
        })
    except Exception as e:
        log.error(f"Caption search failed: {e}")
        return jsonify({"error": str(e)}), 500
