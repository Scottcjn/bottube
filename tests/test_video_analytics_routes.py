from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Generator

import pytest


ROOT = Path(__file__).resolve().parents[1]


class FakeCTRTracker:
    def __init__(self) -> None:
        self.video_ids: list[str] = []

    def get_stats(self, video_id: str) -> None:
        self.video_ids.append(video_id)
        return None


class FakeABManager:
    def __init__(self) -> None:
        self.stats_video_ids: list[str] = []
        self.winner_video_ids: list[str] = []

    def get_variant_stats(self, video_id: str) -> list[dict[str, Any]]:
        self.stats_video_ids.append(video_id)
        return []

    def get_winner(self, video_id: str) -> None:
        self.winner_video_ids.append(video_id)
        return None


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[Any, None, None]:
    db_path = tmp_path / "bottube_video_analytics.db"
    os.environ["BOTTUBE_BASE_DIR"] = str(tmp_path)
    os.environ["BOTTUBE_DB_PATH"] = str(db_path)
    os.environ["BOTTUBE_DB"] = str(db_path)

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    for mod_name in list(sys.modules.keys()):
        if mod_name == "bottube_server" or mod_name.endswith("_blueprint") or mod_name in {
            "paypal_packages",
            "gpu_marketplace",
            "banano_blueprint",
            "captions_blueprint",
        }:
            del sys.modules[mod_name]

    orig_connect = sqlite3.connect

    def redirect_root_db(path: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        if str(path) == "/root/bottube/bottube.db":
            path = db_path
        return orig_connect(path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", redirect_root_db)

    import bottube_server

    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server.app.config["TESTING"] = True
    bottube_server.init_db()
    yield bottube_server.app.test_client()


def _insert_video(video_id: str = "analytics1") -> None:
    import bottube_server

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
            VALUES ('analytics_agent', 'Analytics Agent', 'bottube_sk_analytics', '', '', 1.0, 1.0)
            """
        )
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, description, filename, duration_sec, created_at, is_removed)
            VALUES (?, ?, 'Analytics video', '', 'video.mp4', 8, 1.0, 0)
            """,
            (video_id, int(cur.lastrowid)),
        )
        db.commit()


def test_ctr_stats_returns_404_for_missing_video(client, monkeypatch):
    import bottube_server

    tracker = FakeCTRTracker()
    monkeypatch.setattr(bottube_server, "_get_ctr_tracker", lambda: tracker)

    resp = client.get("/api/videos/missing-video/ctr")

    assert resp.status_code == 404
    assert resp.get_json() == {"ok": False, "error": "Video not found"}
    assert tracker.video_ids == []


def test_ctr_stats_preserves_zero_stats_for_existing_video(client, monkeypatch):
    import bottube_server

    _insert_video()
    tracker = FakeCTRTracker()
    monkeypatch.setattr(bottube_server, "_get_ctr_tracker", lambda: tracker)

    resp = client.get("/api/videos/analytics1/ctr")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "ok": True,
        "video_id": "analytics1",
        "impressions": 0,
        "clicks": 0,
        "ctr": 0,
    }
    assert tracker.video_ids == ["analytics1"]


def test_ab_variants_returns_404_for_missing_video(client, monkeypatch):
    import bottube_server

    manager = FakeABManager()
    monkeypatch.setattr(bottube_server, "_get_ab_manager", lambda: manager)

    resp = client.get("/api/videos/missing-video/ab/variants")

    assert resp.status_code == 404
    assert resp.get_json() == {"ok": False, "error": "Video not found"}
    assert manager.stats_video_ids == []
    assert manager.winner_video_ids == []


def test_ab_variants_preserves_empty_stats_for_existing_video(client, monkeypatch):
    import bottube_server

    _insert_video()
    manager = FakeABManager()
    monkeypatch.setattr(bottube_server, "_get_ab_manager", lambda: manager)

    resp = client.get("/api/videos/analytics1/ab/variants")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "ok": True,
        "video_id": "analytics1",
        "variants": [],
        "winner": None,
    }
    assert manager.stats_video_ids == ["analytics1"]
    assert manager.winner_video_ids == ["analytics1"]
