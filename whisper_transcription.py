"""
BoTTube Whisper Transcription Pipeline (Bounty #750)

Local Whisper-based video transcription using faster-whisper.
Features:
- Background worker that processes new video uploads
- Audio extraction via ffmpeg subprocess
- Transcription with faster-whisper (base model by default)
- Auto language detection
- SRT + VTT + plain text output
- Database storage linked to video
- Idempotent — safe to re-run on existing videos
- Graceful handling of silent/no-audio videos
"""
from __future__ import annotations

import logging
import os
import queue
import sqlite3
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

log = logging.getLogger("bottube.whisper_transcription")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WHISPER_MODEL_SIZE = os.environ.get("BOTTUBE_WHISPER_LOCAL_MODEL", "base")
WHISPER_DEVICE = os.environ.get("BOTTUBE_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("BOTTUBE_WHISPER_COMPUTE_TYPE", "int8")

# How long (seconds) before we consider a transcript stale and re-generate.
# Set to 0 to always use cached version (idempotent by default).
RETRANSCRIBE_AFTER = int(os.environ.get("BOTTUBE_RETRANSCRIBE_AFTER", "0"))

# Workers and queue
_transcription_queue: queue.Queue = queue.Queue()
_worker_thread: Optional[threading.Thread] = None
_worker_lock = threading.Lock()

# Cached model instance (lazy-loaded)
_model = None
_model_lock = threading.Lock()


def _get_db_path() -> str:
    return os.environ.get(
        "BOTTUBE_DB_PATH",
        str(Path(__file__).resolve().parent / "bottube.db"),
    )


def _connect_db() -> sqlite3.Connection:
    db = sqlite3.connect(_get_db_path())
    db.row_factory = sqlite3.Row
    return db


# ---------------------------------------------------------------------------
# Database migration
# ---------------------------------------------------------------------------

def init_transcription_tables() -> None:
    """Create transcript storage tables (idempotent)."""
    with _connect_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS video_transcripts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id     TEXT    NOT NULL,
                language     TEXT    NOT NULL DEFAULT 'unknown',
                language_prob REAL   NOT NULL DEFAULT 0.0,
                plain_text   TEXT    NOT NULL DEFAULT '',
                srt_data     TEXT    NOT NULL DEFAULT '',
                vtt_data     TEXT    NOT NULL DEFAULT '',
                model        TEXT    NOT NULL DEFAULT 'base',
                duration_sec REAL    NOT NULL DEFAULT 0.0,
                source       TEXT    NOT NULL DEFAULT 'faster-whisper',
                created_at   REAL    NOT NULL,
                updated_at   REAL    NOT NULL,
                UNIQUE(video_id)
            )
            """
        )
        # Full-text search index on transcript text
        db.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS video_transcripts_fts
            USING fts5(video_id UNINDEXED, plain_text)
            """
        )
        db.commit()
    log.info("Transcription tables initialized")


# ---------------------------------------------------------------------------
# Whisper model (lazy singleton)
# ---------------------------------------------------------------------------

def _load_model():
    """Load (or return cached) faster-whisper model."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel  # type: ignore
            log.info(
                "Loading faster-whisper model=%s device=%s compute_type=%s",
                WHISPER_MODEL_SIZE,
                WHISPER_DEVICE,
                WHISPER_COMPUTE_TYPE,
            )
            _model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
            )
            log.info("faster-whisper model loaded")
        except ImportError as exc:
            log.error("faster-whisper not installed: %s", exc)
            return None
        except Exception as exc:
            log.error("Failed to load Whisper model: %s", exc)
            return None
    return _model


# ---------------------------------------------------------------------------
# Audio extraction
# ---------------------------------------------------------------------------

def _extract_audio(video_path: str) -> Tuple[Optional[str], float]:
    """Extract audio as 16kHz mono WAV. Returns (wav_path, duration_sec).

    Returns (None, 0.0) if the video has no audio stream or extraction fails.
    """
    # First: check whether the video has an audio stream
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        has_audio = bool(probe.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log.warning("ffprobe failed: %s — assuming no audio", exc)
        has_audio = False

    if not has_audio:
        log.info("No audio stream in %s — skipping transcription", video_path)
        return None, 0.0

    # Get duration
    duration = 0.0
    try:
        dur_probe = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        duration = float(dur_probe.stdout.strip() or "0")
    except Exception:
        pass

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                tmp.name,
            ],
            capture_output=True,
            timeout=120,
            check=True,
        )
        return tmp.name, duration
    except subprocess.CalledProcessError as exc:
        log.error("ffmpeg audio extraction failed for %s: %s", video_path, exc.stderr)
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        return None, duration
    except FileNotFoundError:
        log.error("ffmpeg not found — cannot extract audio")
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        return None, duration


# ---------------------------------------------------------------------------
# SRT / VTT formatting
# ---------------------------------------------------------------------------

def _fmt_vtt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _fmt_srt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _segments_to_vtt(segments: list) -> str:
    lines = ["WEBVTT", ""]
    for idx, seg in enumerate(segments, 1):
        text = str(seg.text).strip()
        if not text:
            continue
        lines.append(str(idx))
        lines.append(f"{_fmt_vtt(seg.start)} --> {_fmt_vtt(seg.end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _segments_to_srt(segments: list) -> str:
    lines = []
    idx = 1
    for seg in segments:
        text = str(seg.text).strip()
        if not text:
            continue
        lines.append(str(idx))
        lines.append(f"{_fmt_srt(seg.start)} --> {_fmt_srt(seg.end)}")
        lines.append(text)
        lines.append("")
        idx += 1
    return "\n".join(lines)


def _segments_to_plain(segments: list) -> str:
    return " ".join(str(seg.text).strip() for seg in segments if str(seg.text).strip())


# ---------------------------------------------------------------------------
# Core transcription
# ---------------------------------------------------------------------------

def transcribe_video(video_id: str, video_path: str, force: bool = False) -> bool:
    """Transcribe a video and store the result in the database.

    Returns True on success (including graceful no-audio skip),
    False on hard failure.

    Idempotent: if a transcript already exists and force=False, returns True
    immediately without re-processing.
    """
    # Check idempotency
    if not force:
        with _connect_db() as db:
            row = db.execute(
                "SELECT id, updated_at FROM video_transcripts WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            if row:
                age = time.time() - (row["updated_at"] or 0)
                if RETRANSCRIBE_AFTER == 0 or age < RETRANSCRIBE_AFTER:
                    log.debug("Transcript already exists for %s — skipping", video_id)
                    return True

    if not os.path.isfile(video_path):
        log.warning("Video file not found: %s", video_path)
        return False

    # Extract audio
    audio_path, duration = _extract_audio(video_path)

    now = time.time()

    if audio_path is None:
        # No audio — store empty transcript (idempotent marker)
        _store_transcript(
            video_id=video_id,
            language="",
            language_prob=0.0,
            plain_text="",
            srt_data="",
            vtt_data="WEBVTT\n",
            duration_sec=duration,
        )
        return True

    try:
        model = _load_model()
        if model is None:
            log.error("Whisper model unavailable — cannot transcribe %s", video_id)
            return False

        log.info("Transcribing %s (%.1fs audio)", video_id, duration)
        segments_gen, info = model.transcribe(
            audio_path,
            beam_size=5,
            language=None,  # auto-detect
            vad_filter=True,  # filter silence
        )
        segments = list(segments_gen)

        language = info.language if info.language else "unknown"
        language_prob = float(info.language_probability) if info.language_probability else 0.0

        plain_text = _segments_to_plain(segments)
        srt_data = _segments_to_srt(segments)
        vtt_data = _segments_to_vtt(segments)

        _store_transcript(
            video_id=video_id,
            language=language,
            language_prob=language_prob,
            plain_text=plain_text,
            srt_data=srt_data,
            vtt_data=vtt_data,
            duration_sec=duration,
        )
        log.info(
            "Transcript stored for %s: lang=%s (%.0f%%), %d chars",
            video_id,
            language,
            language_prob * 100,
            len(plain_text),
        )
        return True

    except Exception as exc:
        log.error("Transcription failed for %s: %s", video_id, exc)
        return False
    finally:
        if audio_path:
            try:
                os.unlink(audio_path)
            except OSError:
                pass


def _store_transcript(
    video_id: str,
    language: str,
    language_prob: float,
    plain_text: str,
    srt_data: str,
    vtt_data: str,
    duration_sec: float,
) -> None:
    now = time.time()
    with _connect_db() as db:
        db.execute(
            """
            INSERT INTO video_transcripts
                (video_id, language, language_prob, plain_text, srt_data, vtt_data,
                 model, duration_sec, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'faster-whisper', ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                language     = excluded.language,
                language_prob = excluded.language_prob,
                plain_text   = excluded.plain_text,
                srt_data     = excluded.srt_data,
                vtt_data     = excluded.vtt_data,
                model        = excluded.model,
                duration_sec = excluded.duration_sec,
                updated_at   = excluded.updated_at
            """,
            (
                video_id, language, language_prob,
                plain_text, srt_data, vtt_data,
                WHISPER_MODEL_SIZE, duration_sec,
                now, now,
            ),
        )
        # Update full-text search index
        try:
            db.execute(
                "DELETE FROM video_transcripts_fts WHERE video_id = ?",
                (video_id,),
            )
            if plain_text:
                db.execute(
                    "INSERT INTO video_transcripts_fts (video_id, plain_text) VALUES (?, ?)",
                    (video_id, plain_text),
                )
        except sqlite3.Error as exc:
            log.warning("FTS index update failed for %s: %s", video_id, exc)
        db.commit()


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _worker_loop() -> None:
    """Process transcription jobs from the queue."""
    log.info("Whisper transcription worker started")
    while True:
        try:
            job = _transcription_queue.get(timeout=5)
            if job is None:
                log.info("Worker received shutdown signal")
                break
            video_id, video_path, force = job
            try:
                transcribe_video(video_id, video_path, force=force)
            except Exception as exc:
                log.error("Worker error processing %s: %s", video_id, exc)
            finally:
                _transcription_queue.task_done()
        except queue.Empty:
            continue
        except Exception as exc:
            log.error("Unexpected worker loop error: %s", exc)


def start_worker() -> None:
    """Start the background transcription worker thread (idempotent)."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="whisper-transcription-worker",
            daemon=True,
        )
        _worker_thread.start()
        log.info("Whisper transcription worker started")


def stop_worker() -> None:
    """Gracefully stop the background worker."""
    _transcription_queue.put(None)


def enqueue_transcription(video_id: str, video_path: str, force: bool = False) -> None:
    """Add a video to the transcription queue.

    Safe to call from any thread. Starts the worker if not already running.
    """
    start_worker()
    _transcription_queue.put((video_id, video_path, force))
    log.debug("Enqueued transcription for %s", video_id)


# ---------------------------------------------------------------------------
# Backfill utility — process existing videos
# ---------------------------------------------------------------------------

def backfill_existing_videos(
    video_dir: Optional[str] = None,
    force: bool = False,
    batch_size: int = 50,
) -> int:
    """Re-transcribe (or transcribe for the first time) all existing videos.

    Args:
        video_dir: Directory containing video files. Falls back to
                   $BOTTUBE_VIDEO_DIR or <db_parent>/videos.
        force: If True, re-transcribe even if a transcript already exists.
        batch_size: Max number of videos to enqueue per call.

    Returns:
        Number of videos enqueued.
    """
    if video_dir is None:
        video_dir = os.environ.get(
            "BOTTUBE_VIDEO_DIR",
            str(Path(_get_db_path()).parent / "videos"),
        )

    start_worker()

    with _connect_db() as db:
        if force:
            rows = db.execute(
                "SELECT video_id, filename FROM videos LIMIT ?",
                (batch_size,),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT v.video_id, v.filename
                FROM videos v
                LEFT JOIN video_transcripts t ON v.video_id = t.video_id
                WHERE t.video_id IS NULL
                LIMIT ?
                """,
                (batch_size,),
            ).fetchall()

    enqueued = 0
    for row in rows:
        video_path = str(Path(video_dir) / row["filename"])
        if os.path.isfile(video_path):
            enqueue_transcription(row["video_id"], video_path, force=force)
            enqueued += 1
        else:
            log.warning("Video file not found during backfill: %s", video_path)

    log.info("Backfill enqueued %d videos (force=%s)", enqueued, force)
    return enqueued


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_transcript(video_id: str) -> Optional[dict]:
    """Return transcript data for a video, or None if not found."""
    with _connect_db() as db:
        row = db.execute(
            """
            SELECT video_id, language, language_prob, plain_text,
                   srt_data, vtt_data, model, duration_sec, source,
                   created_at, updated_at
            FROM video_transcripts
            WHERE video_id = ?
            """,
            (video_id,),
        ).fetchone()
    if not row:
        return None
    return dict(row)


def search_transcripts(query: str, limit: int = 50) -> List[str]:
    """Return video_ids whose transcripts match the query (FTS)."""
    tokens = [t for t in query.lower().split() if t.isalnum()]
    if not tokens:
        return []
    fts_query = " ".join(f'"{t}"' for t in tokens[:8])
    try:
        with _connect_db() as db:
            rows = db.execute(
                """
                SELECT video_id FROM video_transcripts_fts
                WHERE plain_text MATCH ?
                LIMIT ?
                """,
                (fts_query, max(1, min(limit, 500))),
            ).fetchall()
        return [r["video_id"] for r in rows]
    except sqlite3.Error as exc:
        log.warning("Transcript FTS search failed: %s", exc)
        return []
