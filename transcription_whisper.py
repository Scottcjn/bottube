# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import tempfile
import threading
import time
from pathlib import Path

log = logging.getLogger("bottube.transcription")


def init_transcript_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_transcripts (
            video_id TEXT PRIMARY KEY,
            language TEXT DEFAULT 'auto',
            transcript_text TEXT DEFAULT '',
            srt_data TEXT DEFAULT '',
            vtt_data TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            error TEXT DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_transcripts_status ON video_transcripts(status)")


def _extract_audio(video_path: Path) -> Path | None:
    audio = Path(tempfile.mktemp(suffix=".wav"))
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(video_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-y",
                str(audio),
            ],
            capture_output=True,
            check=True,
            timeout=120,
        )
        return audio
    except Exception as exc:
        log.warning("audio extraction failed: %s", exc)
        try:
            audio.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def _format_ts(seconds: float, sep: str = ",") -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{int(s):02d}{sep}{int((s-int(s))*1000):03d}"


def _build_subtitles(segments: list[dict]) -> tuple[str, str, str]:
    text_parts: list[str] = []
    srt_lines: list[str] = []
    vtt_lines: list[str] = ["WEBVTT", ""]

    for i, seg in enumerate(segments, 1):
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue
        text_parts.append(txt)
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))

        srt_lines.extend([str(i), f"{_format_ts(start)} --> {_format_ts(end)}", txt, ""])
        vtt_lines.extend([str(i), f"{_format_ts(start, sep='.') } --> {_format_ts(end, sep='.')}", txt, ""])

    return " ".join(text_parts).strip(), "\n".join(srt_lines).strip(), "\n".join(vtt_lines).strip()


def _transcribe(audio_path: Path) -> tuple[str, str, str, str]:
    """Return (language, text, srt, vtt)."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as exc:
        raise RuntimeError("faster-whisper not installed") from exc

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio_path), vad_filter=True)
    segs = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    text, srt, vtt = _build_subtitles(segs)
    lang = (getattr(info, "language", None) or "auto")
    return lang, text, srt, vtt


def _update_status(db_path: str, video_id: str, *, status: str, language: str = "auto", text: str = "", srt: str = "", vtt: str = "", error: str = "") -> None:
    now = time.time()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO video_transcripts(video_id, language, transcript_text, srt_data, vtt_data, status, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
              language=excluded.language,
              transcript_text=excluded.transcript_text,
              srt_data=excluded.srt_data,
              vtt_data=excluded.vtt_data,
              status=excluded.status,
              error=excluded.error,
              updated_at=excluded.updated_at
            """,
            (video_id, language, text, srt, vtt, status, error, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def process_video(db_path: str, video_id: str, video_path: Path) -> None:
    _update_status(db_path, video_id, status="processing")
    audio = _extract_audio(video_path)
    if not audio:
        _update_status(db_path, video_id, status="failed", error="audio_extract_failed")
        return

    try:
        lang, text, srt, vtt = _transcribe(audio)
        if not text:
            _update_status(db_path, video_id, status="empty", language=lang, error="no_speech_detected")
            return
        _update_status(db_path, video_id, status="done", language=lang, text=text, srt=srt, vtt=vtt)
    except Exception as exc:
        _update_status(db_path, video_id, status="failed", error=str(exc)[:500])
    finally:
        try:
            audio.unlink(missing_ok=True)
        except Exception:
            pass


def enqueue_transcription(db_path: str, video_id: str, video_path: Path) -> None:
    _update_status(db_path, video_id, status="pending")
    t = threading.Thread(target=process_video, args=(db_path, video_id, video_path), daemon=True)
    t.start()
