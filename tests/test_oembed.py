from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Generator

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[Any, None, None]:
    db_path = tmp_path / "bottube_oembed.db"
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


def _insert_video(video_id: str = "oembed1") -> None:
    import bottube_server

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
            VALUES ('embed_agent', 'Embed Agent', 'bottube_sk_embed', '', '', 1.0, 1.0)
            """
        )
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, description, filename, thumbnail,
                 duration_sec, width, height, created_at)
            VALUES (?, ?, 'Embeddable video', '', 'video.mp4', '', 8, 640, 360, 1.0)
            """,
            (video_id, int(cur.lastrowid)),
        )
        db.commit()


def test_oembed_clamps_non_positive_dimensions(client):
    _insert_video()

    resp = client.get(
        "/oembed?url=https://bottube.ai/watch/oembed1&maxwidth=-1&maxheight=0"
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["width"] == 1
    assert data["height"] == 1
    assert 'width="1"' in data["html"]
    assert 'height="1"' in data["html"]


def test_oembed_keeps_existing_upper_dimension_clamps(client):
    _insert_video()

    resp = client.get(
        "/oembed?url=https://bottube.ai/watch/oembed1&maxwidth=99999&maxheight=99999"
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["width"] == 1920
    assert data["height"] == 1080
    assert 'width="1920"' in data["html"]
    assert 'height="1080"' in data["html"]
