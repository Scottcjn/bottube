import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_bootstrap.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server
import captions_blueprint

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_captions_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(captions_blueprint, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(captions_blueprint, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr(captions_blueprint, "GOOGLE_CREDS", "", raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    captions_blueprint.init_captions_tables()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, 1.0, 1.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(agent_id: int, video_id: str, title: str = "Quiet Clip") -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, description, filename, created_at, is_removed)
            VALUES (?, ?, ?, '', ?, ?, 0)
            """,
            (video_id, agent_id, title, f"{video_id}.mp4", time.time()),
        )
        db.commit()


def test_caption_table_migrates_to_multi_format(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy_captions.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE video_captions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                language TEXT DEFAULT 'en',
                format TEXT DEFAULT 'vtt',
                caption_data TEXT NOT NULL,
                source TEXT DEFAULT 'auto',
                created_at REAL NOT NULL,
                UNIQUE(video_id, language)
            )
            """
        )
        db.execute(
            """
            INSERT INTO video_captions
                (video_id, language, format, caption_data, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("vid123", "en", "vtt", "WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nhello", "auto", 1.0),
        )
        db.commit()

    monkeypatch.setattr(captions_blueprint, "DB_PATH", db_path, raising=False)
    captions_blueprint.init_captions_tables()

    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            INSERT INTO video_captions
                (video_id, language, format, caption_data, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("vid123", "en", "srt", "1\n00:00:00,000 --> 00:00:01,000\nhello", "whisper", 2.0),
        )
        rows = db.execute(
            "SELECT format FROM video_captions WHERE video_id = ? ORDER BY format",
            ("vid123",),
        ).fetchall()

    assert [row[0] for row in rows] == ["srt", "vtt"]


def test_caption_endpoints_support_vtt_and_srt(client):
    agent_id = _insert_agent("captain", "bottube_sk_captain")
    _insert_video(agent_id, "captionvid1")

    with sqlite3.connect(bottube_server.DB_PATH) as db:
        db.execute(
            """
            INSERT INTO video_captions
                (video_id, language, format, caption_data, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("captionvid1", "en", "vtt", "WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nretro signal", "whisper", time.time()),
        )
        db.execute(
            """
            INSERT INTO video_captions
                (video_id, language, format, caption_data, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("captionvid1", "en", "srt", "1\n00:00:00,000 --> 00:00:01,000\nretro signal", "whisper", time.time()),
        )
        db.commit()

    vtt_resp = client.get("/api/videos/captionvid1/captions")
    assert vtt_resp.status_code == 200
    assert vtt_resp.headers["Content-Type"].startswith("text/vtt")
    assert "retro signal" in vtt_resp.get_data(as_text=True)

    srt_resp = client.get("/api/videos/captionvid1/captions?format=srt")
    assert srt_resp.status_code == 200
    assert srt_resp.headers["Content-Type"].startswith("text/srt")
    assert "retro signal" in srt_resp.get_data(as_text=True)

    status_resp = client.get("/api/videos/captionvid1/captions/status")
    assert status_resp.status_code == 200
    formats = {row["format"] for row in status_resp.get_json()["captions"]}
    assert formats == {"srt", "vtt"}


def test_api_search_matches_caption_text(client):
    agent_id = _insert_agent("captionsearch", "bottube_sk_captionsearch")
    _insert_video(agent_id, "captionvid2", title="Silent Geometry")

    with sqlite3.connect(bottube_server.DB_PATH) as db:
        db.execute(
            """
            INSERT INTO video_captions
                (video_id, language, format, caption_data, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "captionvid2",
                "en",
                "vtt",
                "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nswamp sermon neon cathedral",
                "whisper",
                time.time(),
            ),
        )
        captions_blueprint._refresh_caption_search_index(
            db,
            "captionvid2",
            "swamp sermon neon cathedral",
        )
        db.commit()

    resp = client.get("/api/search?q=swamp sermon")
    assert resp.status_code == 200
    videos = resp.get_json()["videos"]
    assert len(videos) == 1
    assert videos[0]["video_id"] == "captionvid2"

    caption_resp = client.get("/api/search/captions?q=swamp sermon")
    assert caption_resp.status_code == 200
    assert caption_resp.get_json()["video_ids"] == ["captionvid2"]
