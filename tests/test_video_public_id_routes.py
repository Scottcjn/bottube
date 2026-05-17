import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_BASE_DIR", "/tmp/bottube_test_video_public_id_routes")
os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_video_public_id_routes/bottube.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_public_id_routes.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server._ctr_tracker = None
    bottube_server._ab_manager = None
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent() -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', 0, ?, ?)
            """,
            ("route_bot", "Route Bot", "bottube_sk_route", time.time(), time.time()),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(video_id: str) -> int:
    agent_id = _insert_agent()
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, "Public route video", f"{video_id}.mp4", time.time()),
        )
        db.commit()
        return int(cur.lastrowid)


def test_ctr_stats_uses_public_video_id(client, monkeypatch):
    public_video_id = "public-route-video"
    internal_id = _insert_video(public_video_id)
    assert str(internal_id) != public_video_id

    class FakeCTRTracker:
        def get_stats(self, video_id):
            assert video_id == public_video_id
            return {
                "video_id": video_id,
                "impressions": 4,
                "clicks": 2,
                "ctr": 0.5,
            }

    monkeypatch.setattr(bottube_server, "_get_ctr_tracker", lambda: FakeCTRTracker())

    resp = client.get(f"/api/videos/{public_video_id}/ctr")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["video_id"] == public_video_id
    assert data["ctr"] == 0.5


def test_ab_variants_uses_public_video_id(client, monkeypatch):
    public_video_id = "public-route-video"
    internal_id = _insert_video(public_video_id)
    assert str(internal_id) != public_video_id

    class FakeABManager:
        def get_variant_stats(self, video_id):
            assert video_id == public_video_id
            return [{"variant_key": "a", "impressions": 3, "clicks": 1, "ctr": 1 / 3}]

        def get_winner(self, video_id):
            assert video_id == public_video_id
            return "a"

    monkeypatch.setattr(bottube_server, "_get_ab_manager", lambda: FakeABManager())

    resp = client.get(f"/api/videos/{public_video_id}/ab/variants")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["video_id"] == public_video_id
    assert data["winner"] == "a"
    assert data["variants"][0]["variant_key"] == "a"
