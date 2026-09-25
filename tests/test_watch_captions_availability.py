# SPDX-License-Identifier: MIT
"""Regression tests for Issue #2303: watch page captions track availability.

Asserts that <track kind="captions" ...> is only rendered when an English WebVTT
caption track (language='en', format='vtt') actually exists in video_captions.
"""
from pathlib import Path
import pytest

import bottube_server


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_watch_captions_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', 0, 1.0, 1.0)
            """,
            (agent_name, agent_name.title(), api_key),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(agent_id: int, video_id: str) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, 1.0, 0)
            """,
            (video_id, agent_id, "Test Captions Video", f"{video_id}.mp4"),
        )
        db.commit()


def test_watch_page_omits_track_when_no_captions(client):
    """A video without any captions must not advertise a <track> element."""
    agent_id = _insert_agent("nocapagent", "bottube_sk_nocap")
    _insert_video(agent_id, "vid_nocap_01")

    resp = client.get("/watch/vid_nocap_01")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<track kind="captions"' not in html


def test_watch_page_omits_track_when_only_srt_or_non_english(client):
    """A video with only SRT format or non-English captions must not advertise the English VTT track."""
    agent_id = _insert_agent("srtagent", "bottube_sk_srt")
    _insert_video(agent_id, "vid_srt_only")
    _insert_video(agent_id, "vid_es_vtt")

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        # English SRT only (track endpoint serves VTT)
        db.execute(
            """
            INSERT INTO video_captions (video_id, language, format, caption_data, source, created_at)
            VALUES (?, 'en', 'srt', '1\n00:00:00,000 --> 00:00:01,000\nHello', 'auto', 1.0)
            """,
            ("vid_srt_only",),
        )
        # Spanish VTT only (track endpoint specifies srclang="en")
        db.execute(
            """
            INSERT INTO video_captions (video_id, language, format, caption_data, source, created_at)
            VALUES (?, 'es', 'vtt', 'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHola', 'auto', 1.0)
            """,
            ("vid_es_vtt",),
        )
        db.commit()

    resp_srt = client.get("/watch/vid_srt_only")
    assert resp_srt.status_code == 200
    assert '<track kind="captions"' not in resp_srt.get_data(as_text=True)

    resp_es = client.get("/watch/vid_es_vtt")
    assert resp_es.status_code == 200
    assert '<track kind="captions"' not in resp_es.get_data(as_text=True)


def test_watch_page_renders_track_when_en_vtt_captions_exist(client):
    """A video with valid English VTT captions must advertise the <track> element."""
    agent_id = _insert_agent("vttagent", "bottube_sk_vtt")
    _insert_video(agent_id, "vid_with_captions")

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO video_captions (video_id, language, format, caption_data, source, created_at)
            VALUES (?, 'en', 'vtt', 'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nWelcome to BoTTube', 'auto', 1.0)
            """,
            ("vid_with_captions",),
        )
        db.commit()

    resp = client.get("/watch/vid_with_captions")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert '<track kind="captions"' in html
    assert 'src="/api/videos/vid_with_captions/captions"' in html or 'src="https://bottube.ai/api/videos/vid_with_captions/captions"' in html or '/api/videos/vid_with_captions/captions' in html
    assert 'srclang="en"' in html
    assert 'label="English (auto)"' in html
