# SPDX-License-Identifier: MIT

from __future__ import annotations

import sqlite3

from transcription_whisper import _build_subtitles, init_transcript_tables


def test_build_subtitles_outputs_plain_srt_vtt():
    segments = [
        {"start": 0.0, "end": 1.2, "text": "Hello world"},
        {"start": 1.2, "end": 2.4, "text": "This is a test"},
    ]
    text, srt, vtt = _build_subtitles(segments)
    assert "Hello world" in text
    assert "1\n00:00:00,000 --> 00:00:01,199" in srt
    assert "WEBVTT" in vtt


def test_init_transcript_tables_creates_table():
    conn = sqlite3.connect(":memory:")
    init_transcript_tables(conn)
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_transcripts'").fetchone()
    assert row is not None
