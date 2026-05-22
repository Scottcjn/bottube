import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "BOTTUBE_DB_PATH",
    "/tmp/bottube_test_playlist_visibility_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_playlist_visibility_bootstrap.db",
)

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages  # noqa: E402


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server  # noqa: E402

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_playlist_visibility_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(
    agent_name: str,
    created_at: float,
    *,
    is_banned: int = 0,
) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url,
                 created_at, last_active, is_banned)
            VALUES (?, ?, ?, '', '', ?, ?, ?)
            """,
            (
                agent_name,
                agent_name.replace("-", " ").title(),
                f"bottube_sk_{agent_name}",
                created_at,
                created_at,
                is_banned,
            ),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(
    video_id: str,
    agent_id: int,
    title: str,
    created_at: float,
    *,
    is_removed: int = 0,
) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, thumbnail, created_at,
                 views, is_removed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                agent_id,
                title,
                f"{video_id}.mp4",
                f"{video_id}.jpg",
                created_at,
                int(created_at),
                is_removed,
            ),
        )
        db.commit()


def _insert_playlist(
    playlist_id: str,
    agent_id: int,
    title: str,
    *,
    visibility: str = "public",
) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        now = time.time()
        cur = db.execute(
            """
            INSERT INTO playlists
                (playlist_id, agent_id, title, description, visibility,
                 created_at, updated_at)
            VALUES (?, ?, ?, '', ?, ?, ?)
            """,
            (playlist_id, agent_id, title, visibility, now, now),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_playlist_item(
    playlist_db_id: int,
    video_id: str,
    position: int,
) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO playlist_items
                (playlist_id, video_id, position, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (playlist_db_id, video_id, position, time.time()),
        )
        db.commit()


def _headers(agent_name: str) -> dict[str, str]:
    return {"X-API-Key": f"bottube_sk_{agent_name}"}


def test_public_playlist_hides_removed_and_banned_owner_videos(client):
    owner_id = _insert_agent("playlist-owner", 1000.0)
    visible_creator_id = _insert_agent("visible-creator", 1001.0)
    banned_creator_id = _insert_agent("banned-creator", 1002.0, is_banned=1)
    playlist_db_id = _insert_playlist("playlistvis1", owner_id, "Public Mix")
    _insert_video("visiblevid01", visible_creator_id, "Visible Video", 1003.0)
    _insert_video(
        "removedvid01",
        visible_creator_id,
        "Removed Video",
        1004.0,
        is_removed=1,
    )
    _insert_video("bannedvid01", banned_creator_id, "Banned Video", 1005.0)
    _insert_playlist_item(playlist_db_id, "removedvid01", 1)
    _insert_playlist_item(playlist_db_id, "bannedvid01", 2)
    _insert_playlist_item(playlist_db_id, "visiblevid01", 3)

    resp = client.get("/api/playlists/playlistvis1")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["item_count"] == 1
    assert [item["video_id"] for item in data["items"]] == ["visiblevid01"]


def test_playlist_page_hides_removed_and_banned_owner_videos(client):
    owner_id = _insert_agent("playlist-owner", 1000.0)
    visible_creator_id = _insert_agent("visible-creator", 1001.0)
    banned_creator_id = _insert_agent("banned-creator", 1002.0, is_banned=1)
    playlist_db_id = _insert_playlist("playlistpg1", owner_id, "Public Mix")
    _insert_video("visiblevid01", visible_creator_id, "Visible Video", 1003.0)
    _insert_video(
        "removedvid01",
        visible_creator_id,
        "Removed Video",
        1004.0,
        is_removed=1,
    )
    _insert_video("bannedvid01", banned_creator_id, "Banned Video", 1005.0)
    _insert_playlist_item(playlist_db_id, "visiblevid01", 1)
    _insert_playlist_item(playlist_db_id, "removedvid01", 2)
    _insert_playlist_item(playlist_db_id, "bannedvid01", 3)

    resp = client.get("/playlist/playlistpg1")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Visible Video" in body
    assert "Removed Video" not in body
    assert "Banned Video" not in body


def test_public_agent_playlist_counts_only_visible_items(client):
    owner_id = _insert_agent("playlist-owner", 1000.0)
    visible_creator_id = _insert_agent("visible-creator", 1001.0)
    banned_creator_id = _insert_agent("banned-creator", 1002.0, is_banned=1)
    playlist_db_id = _insert_playlist("playlistcount1", owner_id, "Public Mix")
    _insert_video("visiblevid01", visible_creator_id, "Visible Video", 1003.0)
    _insert_video(
        "removedvid01",
        visible_creator_id,
        "Removed Video",
        1004.0,
        is_removed=1,
    )
    _insert_video("bannedvid01", banned_creator_id, "Banned Video", 1005.0)
    _insert_playlist_item(playlist_db_id, "visiblevid01", 1)
    _insert_playlist_item(playlist_db_id, "removedvid01", 2)
    _insert_playlist_item(playlist_db_id, "bannedvid01", 3)

    resp = client.get("/api/agents/playlist-owner/playlists")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["playlists"][0]["item_count"] == 1


def test_add_playlist_item_rejects_hidden_videos(client):
    owner_id = _insert_agent("playlist-owner", 1000.0)
    visible_creator_id = _insert_agent("visible-creator", 1001.0)
    banned_creator_id = _insert_agent("banned-creator", 1002.0, is_banned=1)
    _insert_playlist("playlistadd1", owner_id, "Editable Mix")
    _insert_video("visiblevid01", visible_creator_id, "Visible Video", 1003.0)
    _insert_video(
        "removedvid01",
        visible_creator_id,
        "Removed Video",
        1004.0,
        is_removed=1,
    )
    _insert_video("bannedvid01", banned_creator_id, "Banned Video", 1005.0)

    removed_resp = client.post(
        "/api/playlists/playlistadd1/items",
        headers=_headers("playlist-owner"),
        json={"video_id": "removedvid01"},
    )
    banned_resp = client.post(
        "/api/playlists/playlistadd1/items",
        headers=_headers("playlist-owner"),
        json={"video_id": "bannedvid01"},
    )
    visible_resp = client.post(
        "/api/playlists/playlistadd1/items",
        headers=_headers("playlist-owner"),
        json={"video_id": "visiblevid01"},
    )

    assert removed_resp.status_code == 400
    assert banned_resp.status_code == 400
    assert visible_resp.status_code == 201
