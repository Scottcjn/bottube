"""
Tests for BoTTube Whisper Transcription Pipeline (Bounty #750)

Covers:
- DB table initialization (idempotent)
- Audio extraction (with/without audio stream)
- SRT / VTT / plain text formatting
- Transcript storage and retrieval
- Idempotency (re-run doesn't duplicate)
- Background worker enqueue
- FTS search
- API endpoints (via Flask test client)
- Backfill utility
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Redirect DB before any imports that trigger sqlite3.connect
os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_whisper_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_whisper_bootstrap.db")

import whisper_transcription as wt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated temporary database for each test."""
    db_file = tmp_path / "test_wt.db"
    monkeypatch.setattr(wt, "_get_db_path", lambda: str(db_file))
    wt.init_transcription_tables()
    return db_file


@pytest.fixture()
def video_dir(tmp_path):
    vdir = tmp_path / "videos"
    vdir.mkdir()
    return vdir


@pytest.fixture()
def silent_video(video_dir):
    """A video file that has no audio stream (simulated with ffmpeg)."""
    path = video_dir / "silent.mp4"
    # Create a 1-second silent video using ffmpeg (video-only, no audio)
    result = os.system(
        f"ffmpeg -y -f lavfi -i color=c=black:size=64x64:rate=10:duration=1 "
        f"-an {path} -loglevel quiet 2>/dev/null"
    )
    if not path.exists():
        pytest.skip("ffmpeg not available or failed to create test video")
    return path


@pytest.fixture()
def audio_video(video_dir):
    """A video file that has a sine-wave audio stream."""
    path = video_dir / "audio.mp4"
    result = os.system(
        f"ffmpeg -y "
        f"-f lavfi -i color=c=blue:size=64x64:rate=10:duration=2 "
        f"-f lavfi -i 'sine=frequency=440:duration=2' "
        f"-shortest {path} -loglevel quiet 2>/dev/null"
    )
    if not path.exists():
        pytest.skip("ffmpeg not available or failed to create test video")
    return path


# ---------------------------------------------------------------------------
# Unit tests: table init
# ---------------------------------------------------------------------------

def test_init_transcription_tables_is_idempotent(tmp_db):
    """Calling init twice must not raise."""
    wt.init_transcription_tables()
    wt.init_transcription_tables()
    with sqlite3.connect(str(tmp_db)) as db:
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='video_transcripts'"
        ).fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# Unit tests: formatting helpers
# ---------------------------------------------------------------------------

class _FakeSeg:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


def test_fmt_vtt_time():
    assert wt._fmt_vtt(0.0) == "00:00:00.000"
    assert wt._fmt_vtt(3661.5) == "01:01:01.500"


def test_fmt_srt_time():
    assert wt._fmt_srt(0.0) == "00:00:00,000"
    assert wt._fmt_srt(3661.5) == "01:01:01,500"


def test_segments_to_vtt():
    segs = [_FakeSeg(0.0, 1.5, "hello world")]
    vtt = wt._segments_to_vtt(segs)
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.500" in vtt
    assert "hello world" in vtt


def test_segments_to_srt():
    segs = [_FakeSeg(0.0, 1.5, "hello world")]
    srt = wt._segments_to_srt(segs)
    assert "1\n" in srt
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "hello world" in srt


def test_segments_to_plain():
    segs = [_FakeSeg(0, 1, "hello"), _FakeSeg(1, 2, "world")]
    assert wt._segments_to_plain(segs) == "hello world"


def test_segments_skip_empty_text():
    segs = [_FakeSeg(0, 1, ""), _FakeSeg(1, 2, "  "), _FakeSeg(2, 3, "hi")]
    vtt = wt._segments_to_vtt(segs)
    assert "hi" in vtt
    # Blank segments should not appear in SRT either
    srt = wt._segments_to_srt(segs)
    assert "hi" in srt
    # Plain text should only have 'hi'
    assert wt._segments_to_plain(segs) == "hi"


# ---------------------------------------------------------------------------
# Unit tests: audio extraction
# ---------------------------------------------------------------------------

def test_extract_audio_no_audio_stream(silent_video):
    audio_path, duration = wt._extract_audio(str(silent_video))
    assert audio_path is None  # no audio stream → graceful None
    assert isinstance(duration, float)


def test_extract_audio_with_audio_stream(audio_video):
    audio_path, duration = wt._extract_audio(str(audio_video))
    assert audio_path is not None
    assert os.path.isfile(audio_path)
    assert duration > 0
    # Cleanup
    os.unlink(audio_path)


def test_extract_audio_missing_file():
    audio_path, duration = wt._extract_audio("/nonexistent/path/video.mp4")
    # Should fail gracefully
    assert audio_path is None


# ---------------------------------------------------------------------------
# Unit tests: transcribe_video (mocked model)
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_model():
    """Fake faster-whisper model."""
    seg = _FakeSeg(0.0, 1.5, "test transcription")
    info = MagicMock()
    info.language = "en"
    info.language_probability = 0.99
    model = MagicMock()
    model.transcribe.return_value = ([seg], info)
    return model


def test_transcribe_video_with_audio(tmp_db, monkeypatch, audio_video, mock_model):
    """Full pipeline: audio extraction → whisper → DB store."""
    monkeypatch.setattr(wt, "_load_model", lambda: mock_model)
    result = wt.transcribe_video("vid001", str(audio_video))
    assert result is True

    transcript = wt.get_transcript("vid001")
    assert transcript is not None
    assert transcript["language"] == "en"
    assert transcript["plain_text"] == "test transcription"
    assert "WEBVTT" in transcript["vtt_data"]
    assert "test transcription" in transcript["srt_data"]


def test_transcribe_video_silent(tmp_db, silent_video):
    """Silent video should store empty transcript and return True."""
    result = wt.transcribe_video("vid_silent", str(silent_video))
    assert result is True

    transcript = wt.get_transcript("vid_silent")
    assert transcript is not None
    assert transcript["plain_text"] == ""
    assert transcript["language"] == ""


def test_transcribe_video_missing_file(tmp_db):
    """Missing file returns False without crashing."""
    result = wt.transcribe_video("vid_missing", "/no/such/file.mp4")
    assert result is False


def test_transcribe_video_idempotent(tmp_db, monkeypatch, audio_video, mock_model):
    """Re-running transcription without force=True should skip re-processing."""
    monkeypatch.setattr(wt, "_load_model", lambda: mock_model)
    wt.transcribe_video("vid_idem", str(audio_video))
    call_count_before = mock_model.transcribe.call_count

    # Re-run (idempotent)
    wt.transcribe_video("vid_idem", str(audio_video))
    assert mock_model.transcribe.call_count == call_count_before  # not called again


def test_transcribe_video_force_reruns(tmp_db, monkeypatch, audio_video, mock_model):
    """force=True must re-transcribe even if transcript exists."""
    monkeypatch.setattr(wt, "_load_model", lambda: mock_model)
    wt.transcribe_video("vid_force", str(audio_video))
    call_count_before = mock_model.transcribe.call_count

    wt.transcribe_video("vid_force", str(audio_video), force=True)
    assert mock_model.transcribe.call_count > call_count_before


def test_transcribe_video_no_model(tmp_db, monkeypatch, audio_video):
    """If model can't be loaded, return False gracefully."""
    monkeypatch.setattr(wt, "_load_model", lambda: None)
    result = wt.transcribe_video("vid_nomodel", str(audio_video))
    assert result is False


# ---------------------------------------------------------------------------
# Unit tests: FTS search
# ---------------------------------------------------------------------------

def test_search_transcripts(tmp_db, monkeypatch, audio_video, mock_model):
    monkeypatch.setattr(wt, "_load_model", lambda: mock_model)
    wt.transcribe_video("vid_search", str(audio_video))

    results = wt.search_transcripts("transcription")
    assert "vid_search" in results


def test_search_transcripts_no_match(tmp_db):
    results = wt.search_transcripts("xyznonexistent")
    assert results == []


def test_search_transcripts_empty_query(tmp_db):
    results = wt.search_transcripts("")
    assert results == []


# ---------------------------------------------------------------------------
# Unit tests: background worker
# ---------------------------------------------------------------------------

def test_enqueue_transcription(tmp_db, monkeypatch, audio_video, mock_model):
    """Enqueued jobs should be processed by the worker thread."""
    monkeypatch.setattr(wt, "_load_model", lambda: mock_model)

    done_event = threading.Event()
    original_transcribe = wt.transcribe_video

    def mock_transcribe(video_id, video_path, force=False):
        r = original_transcribe(video_id, video_path, force=force)
        done_event.set()
        return r

    monkeypatch.setattr(wt, "transcribe_video", mock_transcribe)

    wt.enqueue_transcription("vid_worker", str(audio_video))
    assert done_event.wait(timeout=15), "Worker did not process job within timeout"


def test_start_worker_idempotent():
    """Calling start_worker() multiple times doesn't spawn duplicate threads."""
    wt.start_worker()
    first_thread = wt._worker_thread
    wt.start_worker()
    assert wt._worker_thread is first_thread


# ---------------------------------------------------------------------------
# Unit tests: backfill
# ---------------------------------------------------------------------------

def test_backfill_existing_videos(tmp_db, monkeypatch, video_dir, mock_model):
    """Backfill picks up un-transcribed videos from the database."""
    monkeypatch.setattr(wt, "_load_model", lambda: mock_model)

    # Create a fake video file and DB row
    fake_video = video_dir / "fake001.mp4"
    os.system(
        f"ffmpeg -y -f lavfi -i 'sine=frequency=440:duration=1' "
        f"-f lavfi -i color=c=black:size=64x64:rate=10:duration=1 "
        f"-shortest {fake_video} -loglevel quiet 2>/dev/null"
    )
    if not fake_video.exists():
        pytest.skip("ffmpeg unavailable")

    # Ensure the videos table exists in our test DB
    with wt._connect_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY,
                video_id TEXT UNIQUE NOT NULL,
                agent_id INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                filename TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        db.execute(
            """
            INSERT OR IGNORE INTO videos
                (video_id, agent_id, title, description, filename, created_at)
            VALUES ('backfill_vid', 1, 'Test', '', 'fake001.mp4', ?)
            """,
            (time.time(),),
        )
        db.commit()

    enqueued = wt.backfill_existing_videos(video_dir=str(video_dir), batch_size=10)
    assert enqueued >= 1


# ---------------------------------------------------------------------------
# Integration tests: Flask blueprint endpoints
# ---------------------------------------------------------------------------

@pytest.fixture()
def flask_client(tmp_db, monkeypatch, tmp_path):
    """Flask test client with whisper blueprint registered."""
    import importlib
    import whisper_transcription_blueprint as wtb

    monkeypatch.setattr(wtb.wt, "_get_db_path", lambda: str(tmp_db))

    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(wtb.whisper_bp)
    app.config["TESTING"] = True
    return app.test_client()


def test_get_transcript_not_found(flask_client):
    resp = flask_client.get("/api/videos/nonexistent/transcript")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "error" in data


def test_get_transcript_text_not_found(flask_client):
    resp = flask_client.get("/api/videos/nonexistent/transcript/text")
    assert resp.status_code == 404


def test_get_transcript_srt_not_found(flask_client):
    resp = flask_client.get("/api/videos/nonexistent/transcript/srt")
    assert resp.status_code == 404


def test_get_transcript_vtt_not_found(flask_client):
    resp = flask_client.get("/api/videos/nonexistent/transcript/vtt")
    assert resp.status_code == 404


def test_get_transcript_returns_data(tmp_db, flask_client, monkeypatch):
    """After storing a transcript, the API should return it."""
    import whisper_transcription_blueprint as wtb
    monkeypatch.setattr(wtb.wt, "_get_db_path", lambda: str(tmp_db))

    wt._store_transcript(
        video_id="api_vid_001",
        language="en",
        language_prob=0.95,
        plain_text="hello from api",
        srt_data="1\n00:00:00,000 --> 00:00:01,000\nhello from api\n",
        vtt_data="WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nhello from api\n",
        duration_sec=2.0,
    )

    resp = flask_client.get("/api/videos/api_vid_001/transcript")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["language"] == "en"
    assert data["plain_text"] == "hello from api"
    assert data["has_srt"] is True
    assert data["has_vtt"] is True


def test_get_transcript_text_endpoint(tmp_db, flask_client, monkeypatch):
    import whisper_transcription_blueprint as wtb
    monkeypatch.setattr(wtb.wt, "_get_db_path", lambda: str(tmp_db))

    wt._store_transcript(
        video_id="api_vid_002", language="fr", language_prob=0.8,
        plain_text="bonjour monde", srt_data="", vtt_data="WEBVTT\n",
        duration_sec=1.0,
    )
    resp = flask_client.get("/api/videos/api_vid_002/transcript/text")
    assert resp.status_code == 200
    assert "bonjour monde" in resp.get_data(as_text=True)


def test_get_transcript_srt_endpoint(tmp_db, flask_client, monkeypatch):
    import whisper_transcription_blueprint as wtb
    monkeypatch.setattr(wtb.wt, "_get_db_path", lambda: str(tmp_db))

    wt._store_transcript(
        video_id="api_vid_003", language="de", language_prob=0.9,
        plain_text="hallo", srt_data="1\n00:00:00,000 --> 00:00:01,000\nhallo\n",
        vtt_data="WEBVTT\n", duration_sec=1.0,
    )
    resp = flask_client.get("/api/videos/api_vid_003/transcript/srt")
    assert resp.status_code == 200
    assert "hallo" in resp.get_data(as_text=True)


def test_get_transcript_vtt_endpoint(tmp_db, flask_client, monkeypatch):
    import whisper_transcription_blueprint as wtb
    monkeypatch.setattr(wtb.wt, "_get_db_path", lambda: str(tmp_db))

    wt._store_transcript(
        video_id="api_vid_004", language="ja", language_prob=0.85,
        plain_text="konnichiwa", srt_data="",
        vtt_data="WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nkonnichiwa\n",
        duration_sec=1.0,
    )
    resp = flask_client.get("/api/videos/api_vid_004/transcript/vtt")
    assert resp.status_code == 200
    assert "WEBVTT" in resp.get_data(as_text=True)
    assert "konnichiwa" in resp.get_data(as_text=True)


def test_search_endpoint(tmp_db, flask_client, monkeypatch):
    import whisper_transcription_blueprint as wtb
    monkeypatch.setattr(wtb.wt, "_get_db_path", lambda: str(tmp_db))

    wt._store_transcript(
        video_id="search_vid_001", language="en", language_prob=0.99,
        plain_text="unicorn rainbow galaxy", srt_data="", vtt_data="WEBVTT\n",
        duration_sec=3.0,
    )
    resp = flask_client.get("/api/transcript/search?q=unicorn")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "search_vid_001" in data["video_ids"]


def test_search_endpoint_no_query(flask_client):
    resp = flask_client.get("/api/transcript/search")
    assert resp.status_code == 400


def test_trigger_transcription_video_not_found(flask_client):
    resp = flask_client.post("/api/videos/nosuchvid/transcript/trigger", json={})
    assert resp.status_code == 404
