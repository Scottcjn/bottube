"""
BoTTube auto-captions with provider fallback.

Supports:
- OpenAI Whisper when OPENAI_API_KEY is configured
- Google Cloud Speech-to-Text as a fallback when
  GOOGLE_APPLICATION_CREDENTIALS is configured

Captions are stored in both WebVTT and SRT formats and indexed for search.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.request

import requests
from flask import Blueprint, current_app, jsonify, request


log = logging.getLogger("bottube.captions")

captions_bp = Blueprint("captions", __name__)

GOOGLE_CREDS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
SPEECH_API_URL = "https://speech.googleapis.com/v1/speech:recognize"
SPEECH_LONG_API_URL = "https://speech.googleapis.com/v1/speech:longrunningrecognize"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
WHISPER_API_URL = "https://api.openai.com/v1/audio/transcriptions"
WHISPER_MODEL = os.environ.get("BOTTUBE_WHISPER_MODEL", "whisper-1")

DB_PATH = os.environ.get("BOTTUBE_DB_PATH") or os.environ.get("BOTTUBE_DB") or "/root/bottube/bottube.db"


def _db_path() -> str:
    return str(DB_PATH)


def _connect_db() -> sqlite3.Connection:
    db = sqlite3.connect(_db_path())
    db.row_factory = sqlite3.Row
    return db


def _table_exists(db: sqlite3.Connection, name: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _normalized_sql(sql: str) -> str:
    return re.sub(r"\s+", "", (sql or "").lower())


def _migrate_captions_table(db: sqlite3.Connection) -> None:
    target_sql = """
        CREATE TABLE IF NOT EXISTS video_captions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            language TEXT DEFAULT 'en',
            format TEXT DEFAULT 'vtt',
            caption_data TEXT NOT NULL,
            source TEXT DEFAULT 'auto',
            created_at REAL NOT NULL,
            UNIQUE(video_id, language, format)
        )
    """

    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'video_captions'"
    ).fetchone()
    if not row:
        db.execute(target_sql)
        return

    if "unique(video_id,language,format)" in _normalized_sql(row["sql"]):
        return

    db.execute("ALTER TABLE video_captions RENAME TO video_captions_legacy")
    db.execute(target_sql)
    db.execute(
        """
        INSERT OR IGNORE INTO video_captions
            (video_id, language, format, caption_data, source, created_at)
        SELECT
            video_id,
            COALESCE(language, 'en'),
            COALESCE(format, 'vtt'),
            caption_data,
            COALESCE(source, 'auto'),
            created_at
        FROM video_captions_legacy
        """
    )
    db.execute("DROP TABLE video_captions_legacy")


def _rebuild_caption_search_index(db: sqlite3.Connection) -> None:
    try:
        db.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS video_captions_fts
            USING fts5(video_id UNINDEXED, caption_data)
            """
        )
        db.execute("DELETE FROM video_captions_fts")
        rows = db.execute(
            """
            SELECT video_id, GROUP_CONCAT(caption_data, ' ') AS caption_blob
            FROM video_captions
            GROUP BY video_id
            """
        ).fetchall()
        for row in rows:
            db.execute(
                "INSERT INTO video_captions_fts (video_id, caption_data) VALUES (?, ?)",
                (row["video_id"], row["caption_blob"] or ""),
            )
    except sqlite3.Error as exc:
        log.warning("Caption FTS init failed: %s", exc)


def init_captions_tables() -> None:
    """Create or migrate captions storage and search tables."""
    with _connect_db() as db:
        _migrate_captions_table(db)
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_video_captions_video ON video_captions(video_id)"
        )
        _rebuild_caption_search_index(db)
        db.commit()
    log.info("Captions tables initialized")


def _extract_audio(video_path: str) -> str:
    """Extract audio from a video as 16kHz mono WAV."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                video_path,
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                tmp.name,
            ],
            capture_output=True,
            timeout=120,
            check=True,
        )
        return tmp.name
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        log.error("Audio extraction failed: %s", exc)
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        return ""


def _get_access_token() -> str:
    """Get a Google Cloud access token."""
    if not GOOGLE_CREDS or not os.path.exists(GOOGLE_CREDS):
        return ""
    try:
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    try:
        from google_indexing import _get_access_token as get_token

        return get_token("https://www.googleapis.com/auth/cloud-platform")
    except Exception as exc:
        log.error("Failed to get Google access token: %s", exc)
    return ""


def _google_words_to_cues(words: list[dict]) -> list[dict]:
    """Group Google word timestamps into subtitle cues."""
    if not words:
        return []

    cues = []
    cue_words = []
    cue_start = 0.0

    for word in words:
        if not cue_words:
            cue_start = word["start"]
        cue_words.append(word["word"])

        elapsed = word["end"] - cue_start
        is_sentence_end = word["word"].endswith((".", "!", "?"))
        if elapsed >= 5.0 or (elapsed >= 3.0 and is_sentence_end) or len(cue_words) >= 15:
            cues.append(
                {
                    "start": cue_start,
                    "end": word["end"],
                    "text": " ".join(cue_words).strip(),
                }
            )
            cue_words = []

    if cue_words:
        cues.append(
            {
                "start": cue_start,
                "end": words[-1]["end"],
                "text": " ".join(cue_words).strip(),
            }
        )

    return [cue for cue in cues if cue["text"]]


def _whisper_segments_to_cues(segments: list[dict]) -> list[dict]:
    cues = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        cues.append(
            {
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
                "text": text,
            }
        )
    return cues


def _format_vtt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def _format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _cues_to_vtt(cues: list[dict]) -> str:
    lines = ["WEBVTT", ""]
    for idx, cue in enumerate(cues, start=1):
        lines.append(str(idx))
        lines.append(f"{_format_vtt_time(cue['start'])} --> {_format_vtt_time(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")
    return "\n".join(lines)


def _cues_to_srt(cues: list[dict]) -> str:
    lines = []
    for idx, cue in enumerate(cues, start=1):
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(cue['start'])} --> {_format_srt_time(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")
    return "\n".join(lines)


def _speech_to_text_google(audio_path: str) -> list[dict]:
    token = _get_access_token()
    if not token:
        return []

    with open(audio_path, "rb") as handle:
        audio_bytes = handle.read()
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    duration_sec = max(1, len(audio_bytes) // (16000 * 2))
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

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
    except Exception as exc:
        log.error("Google STT failed: %s", exc)
        return []

    if "name" in result and api_url == SPEECH_LONG_API_URL:
        op_name = result["name"]
        for _ in range(60):
            time.sleep(5)
            poll_req = urllib.request.Request(
                f"https://speech.googleapis.com/v1/operations/{op_name}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(poll_req, timeout=30) as resp:
                result = json.loads(resp.read())
            if result.get("done"):
                result = result.get("response", result)
                break

    words = []
    for alt in result.get("results", []):
        best = alt.get("alternatives", [{}])[0]
        for word in best.get("words", []):
            words.append(
                {
                    "word": word["word"],
                    "start": float(str(word.get("startTime", "0s")).rstrip("s")),
                    "end": float(str(word.get("endTime", "0s")).rstrip("s")),
                }
            )
    return words


def _speech_to_text_whisper(audio_path: str) -> dict:
    if not OPENAI_API_KEY:
        return {}

    try:
        with open(audio_path, "rb") as handle:
            response = requests.post(
                WHISPER_API_URL,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                data={"model": WHISPER_MODEL, "response_format": "verbose_json"},
                files={"file": (os.path.basename(audio_path), handle, "audio/wav")},
                timeout=300,
            )
        response.raise_for_status()
        result = response.json()
        log.info("Whisper transcription succeeded with %s segments", len(result.get("segments", [])))
        return result
    except requests.RequestException as exc:
        log.error("Whisper API failed: %s", exc)
    except ValueError as exc:
        log.error("Whisper JSON decode failed: %s", exc)
    return {}


def _refresh_caption_search_index(db: sqlite3.Connection, video_id: str, text: str) -> None:
    try:
        db.execute("DELETE FROM video_captions_fts WHERE video_id = ?", (video_id,))
        db.execute(
            "INSERT INTO video_captions_fts (video_id, caption_data) VALUES (?, ?)",
            (video_id, text or ""),
        )
    except sqlite3.Error as exc:
        log.warning("Caption search index update failed for %s: %s", video_id, exc)


def _caption_provider():
    if OPENAI_API_KEY:
        return "whisper"
    if GOOGLE_CREDS:
        return "google"
    return None


def generate_captions_for_video(video_id: str, video_path: str) -> bool:
    """Generate captions and store both VTT and SRT tracks."""
    provider = _caption_provider()
    if not provider:
        return False

    audio_path = _extract_audio(video_path)
    if not audio_path:
        return False

    try:
        if provider == "whisper":
            result = _speech_to_text_whisper(audio_path)
            cues = _whisper_segments_to_cues(result.get("segments", []))
            full_text = str(result.get("text", "")).strip()
        else:
            words = _speech_to_text_google(audio_path)
            cues = _google_words_to_cues(words)
            full_text = " ".join(word["word"] for word in words).strip()

        if not cues:
            log.warning("No speech detected for %s", video_id)
            return False

        now = time.time()
        vtt = _cues_to_vtt(cues)
        srt = _cues_to_srt(cues)
        search_text = full_text or " ".join(cue["text"] for cue in cues)

        with _connect_db() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO video_captions
                    (video_id, language, format, caption_data, source, created_at)
                VALUES (?, 'en', 'vtt', ?, ?, ?)
                """,
                (video_id, vtt, provider, now),
            )
            db.execute(
                """
                INSERT OR REPLACE INTO video_captions
                    (video_id, language, format, caption_data, source, created_at)
                VALUES (?, 'en', 'srt', ?, ?, ?)
                """,
                (video_id, srt, provider, now),
            )
            _refresh_caption_search_index(db, video_id, search_text)
            db.commit()
        log.info("Generated %s captions for %s", provider, video_id)
        return True
    finally:
        try:
            os.unlink(audio_path)
        except OSError:
            pass


def generate_captions_async(video_id: str, video_path: str) -> None:
    """Fire-and-forget captions generation."""
    if not _caption_provider():
        return
    thread = threading.Thread(
        target=generate_captions_for_video,
        args=(video_id, video_path),
        daemon=True,
    )
    thread.start()


def _fts_query(raw_query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+", raw_query.lower())
    if not tokens:
        return ""
    return " ".join(f'"{token}"' for token in tokens[:8])


def find_caption_video_ids(query: str, limit: int = 200) -> list[str]:
    fts_query = _fts_query(query)
    try:
        with _connect_db() as db:
            if not fts_query or not _table_exists(db, "video_captions_fts"):
                return []
            rows = db.execute(
                """
                SELECT DISTINCT video_id
                FROM video_captions_fts
                WHERE caption_data MATCH ?
                LIMIT ?
                """,
                (fts_query, max(1, min(limit, 500))),
            ).fetchall()
            return [row["video_id"] for row in rows]
    except sqlite3.Error as exc:
        log.warning("Caption search failed: %s", exc)
        return []


@captions_bp.route("/api/videos/<video_id>/captions")
def get_captions(video_id):
    """Serve VTT or SRT captions for a video."""
    lang = request.args.get("lang", "en")
    fmt = request.args.get("format", "vtt").lower()
    if fmt not in {"vtt", "srt"}:
        return jsonify({"error": "format must be 'vtt' or 'srt'"}), 400

    with _connect_db() as db:
        row = db.execute(
            """
            SELECT caption_data
            FROM video_captions
            WHERE video_id = ? AND language = ? AND format = ?
            """,
            (video_id, lang, fmt),
        ).fetchone()

    if not row:
        return "", 404

    mimetype = "text/srt" if fmt == "srt" else "text/vtt"
    return current_app.response_class(
        row["caption_data"],
        mimetype=mimetype,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@captions_bp.route("/api/videos/<video_id>/captions/status")
def caption_status(video_id):
    """Check which caption tracks exist for a video."""
    with _connect_db() as db:
        rows = db.execute(
            """
            SELECT language, format, source, created_at
            FROM video_captions
            WHERE video_id = ?
            ORDER BY language, format
            """,
            (video_id,),
        ).fetchall()

    return jsonify(
        {
            "video_id": video_id,
            "captions": [
                {
                    "language": row["language"],
                    "format": row["format"],
                    "source": row["source"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
        }
    )


@captions_bp.route("/api/search/captions")
def search_captions():
    """Search caption text and return matching video ids."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    video_ids = find_caption_video_ids(query, limit=request.args.get("limit", 50, type=int))
    return jsonify({"query": query, "count": len(video_ids), "video_ids": video_ids})
