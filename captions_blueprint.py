"""
BoTTube Auto-Captions via Google Cloud Speech-to-Text

Generates WebVTT captions for videos. Stores in DB and serves via API.
Requires: GOOGLE_APPLICATION_CREDENTIALS env var pointing to service account JSON.

Usage:
    from captions_blueprint import captions_bp, init_captions_tables, generate_captions_for_video
    init_captions_tables()
    app.register_blueprint(captions_bp)
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

log = logging.getLogger("bottube.captions")

captions_bp = Blueprint("captions", __name__)

# Google Cloud Speech-to-Text config
GOOGLE_CREDS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
SPEECH_API_URL = "https://speech.googleapis.com/v1/speech:recognize"
SPEECH_LONG_API_URL = "https://speech.googleapis.com/v1/speech:longrunningrecognize"

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


def init_captions_tables():
    """Create captions tables if they don't exist."""
    db = sqlite3.connect(DB_PATH)
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
    db.commit()
    db.close()
    log.info("Captions tables initialized")


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


def _get_access_token() -> str:
    """Get Google Cloud access token from service account credentials."""
    if not GOOGLE_CREDS or not os.path.exists(GOOGLE_CREDS):
        return ""
    try:
        # Use gcloud or manual JWT signing
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    # Fallback: manual JWT exchange (same pattern as google_indexing.py)
    try:
        from google_indexing import _get_access_token as get_token
        return get_token("https://www.googleapis.com/auth/cloud-platform")
    except Exception as e:
        log.error(f"Failed to get access token: {e}")
    return ""


def _speech_to_text(audio_path: str) -> list:
    """Send audio to Google Cloud Speech-to-Text, return timestamped words."""
    import urllib.request

    token = _get_access_token()
    if not token:
        log.error("No access token available for Speech-to-Text")
        return []

    # Read audio file
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    # Check file size - use long-running API for > 1 minute audio
    duration_sec = len(audio_bytes) / (16000 * 2)  # 16kHz, 16-bit
    api_url = SPEECH_LONG_API_URL if duration_sec > 60 else SPEECH_API_URL

    payload = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": 16000,
            "languageCode": "en-US",
            "enableWordTimeOffsets": True,
            "enableAutomaticPunctuation": True,
            "model": "video",
        },
        "audio": {"content": audio_b64},
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        log.error(f"Speech-to-Text API failed: {e}")
        return []

    # For long-running operations, poll for completion
    if "name" in result and duration_sec > 60:
        op_name = result["name"]
        for _ in range(60):  # Poll for up to 5 minutes
            time.sleep(5)
            poll_url = f"https://speech.googleapis.com/v1/operations/{op_name}"
            poll_req = urllib.request.Request(
                poll_url,
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(poll_req, timeout=30) as resp:
                result = json.loads(resp.read())
            if result.get("done"):
                result = result.get("response", result)
                break

    # Extract timestamped words
    words = []
    for alt in result.get("results", []):
        best = alt.get("alternatives", [{}])[0]
        for w in best.get("words", []):
            start = float(w.get("startTime", "0s").rstrip("s"))
            end = float(w.get("endTime", "0s").rstrip("s"))
            words.append({"word": w["word"], "start": start, "end": end})

    return words


def _words_to_vtt(words: list) -> str:
    """Convert timestamped words to WebVTT format with ~5 second segments."""
    if not words:
        return ""

    lines = ["WEBVTT", ""]
    segment_words = []
    segment_start = 0.0
    cue_num = 1

    for w in words:
        if not segment_words:
            segment_start = w["start"]
        segment_words.append(w["word"])

        # Create a new cue every ~5 seconds or at sentence boundaries
        elapsed = w["end"] - segment_start
        is_sentence_end = w["word"].endswith((".","!","?"))
        if elapsed >= 5.0 or (elapsed >= 3.0 and is_sentence_end) or len(segment_words) >= 15:
            segment_end = w["end"]
            text = " ".join(segment_words)
            lines.append(str(cue_num))
            lines.append(
                f"{_format_vtt_time(segment_start)} --> {_format_vtt_time(segment_end)}"
            )
            lines.append(text)
            lines.append("")
            cue_num += 1
            segment_words = []

    # Flush remaining words
    if segment_words:
        text = " ".join(segment_words)
        lines.append(str(cue_num))
        lines.append(
            f"{_format_vtt_time(segment_start)} --> {_format_vtt_time(words[-1]['end'])}"
        )
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


def _format_vtt_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for WebVTT."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def generate_captions_for_video(video_id: str, video_path: str) -> bool:
    """Generate captions for a video and store in DB. Returns True on success."""
    log.info(f"Generating captions for {video_id}")

    # Extract audio
    audio_path = _extract_audio(video_path)
    if not audio_path:
        return False

    try:
        # Send to Speech-to-Text
        words = _speech_to_text(audio_path)
        if not words:
            log.warning(f"No speech detected in {video_id}")
            return False

        # Convert to WebVTT
        vtt = _words_to_vtt(words)
        if not vtt:
            return False

        # Store in database
        db = sqlite3.connect(DB_PATH)
        db.execute(
            "INSERT OR REPLACE INTO video_captions (video_id, language, format, caption_data, source, created_at) "
            "VALUES (?, 'en', 'vtt', ?, 'auto', ?)",
            (video_id, vtt, time.time()),
        )
        db.commit()
        db.close()
        log.info(f"Captions generated for {video_id}: {len(words)} words")
        return True
    finally:
        try:
            os.unlink(audio_path)
        except OSError:
            pass


def generate_captions_async(video_id: str, video_path: str):
    """Fire-and-forget caption generation in background thread."""
    if not GOOGLE_CREDS:
        return
    t = threading.Thread(
        target=generate_captions_for_video,
        args=(video_id, video_path),
        daemon=True,
    )
    t.start()


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@captions_bp.route("/api/videos/<video_id>/captions")
def get_captions(video_id):
    """Serve WebVTT captions for a video."""
    lang = request.args.get("lang", "en")
    db = _get_db()
    row = db.execute(
        "SELECT caption_data FROM video_captions WHERE video_id = ? AND language = ?",
        (video_id, lang),
    ).fetchone()

    if not row:
        return "", 404

    return current_app.response_class(
        row["caption_data"],
        mimetype="text/vtt",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@captions_bp.route("/api/videos/<video_id>/captions/status")
def caption_status(video_id):
    """Check if captions exist for a video."""
    db = _get_db()
    rows = db.execute(
        "SELECT language, source, created_at FROM video_captions WHERE video_id = ?",
        (video_id,),
    ).fetchall()

    return jsonify({
        "video_id": video_id,
        "captions": [
            {"language": r["language"], "source": r["source"], "created_at": r["created_at"]}
            for r in rows
        ],
    })
