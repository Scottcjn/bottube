# SPDX-License-Identifier: MIT
"""Regression tests for issue #2141 — one shared playlist append operation.

``POST /api/playlists/<id>/items`` and ``POST /playlist/<id>/add`` each carried
their own inline copy of the duplicate check, the position allocation and the
``IntegrityError`` translation. Two copies of one operation are free to drift:
a later fix applied to one route silently leaves the other behind.

Both routes now delegate to ``bottube_server._append_playlist_item()``. These
regressions pin the shared operation and the route contracts that sit on top of
it:

1. The helper itself, driven exactly as the issue describes — initial add,
   duplicate add, second distinct add — returns the allocated position, the
   ``None`` conflict sentinel, and then position ``2``.
2. The helper leaves no extra row behind on the duplicate call.
3. The API route keeps its ``201`` + ``position`` and ``409`` +
   ``"Video already in playlist"`` contract.
4. The web route keeps its ``200`` + ``{"ok": True}`` and ``409`` +
   ``"Already in playlist"`` contract.
5. API and web routes do not drift: appends interleaved across both surfaces
   share one position sequence.
"""
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "BOTTUBE_DB_PATH",
    "/tmp/bottube_test_playlist_shared_append_2141_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_playlist_shared_append_2141_bootstrap.db",
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
    db_path = tmp_path / "bottube_playlist_shared_append_2141_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, created_at: float) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url,
                 created_at, last_active, is_banned)
            VALUES (?, ?, ?, '', '', ?, ?, 0)
            """,
            (
                agent_name,
                agent_name.replace("-", " ").title(),
                f"bottube_sk_{agent_name}",
                created_at,
                created_at,
            ),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(video_id: str, agent_id: int, title: str, created_at: float) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, thumbnail, created_at,
                 views, is_removed)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                video_id,
                agent_id,
                title,
                f"{video_id}.mp4",
                f"{video_id}.jpg",
                created_at,
                int(created_at),
            ),
        )
        db.commit()


def _insert_playlist(playlist_id: str, agent_id: int, title: str) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        now = time.time()
        cur = db.execute(
            """
            INSERT INTO playlists
                (playlist_id, agent_id, title, description, visibility,
                 created_at, updated_at)
            VALUES (?, ?, ?, '', 'public', ?, ?)
            """,
            (playlist_id, agent_id, title, now, now),
        )
        db.commit()
        return int(cur.lastrowid)


def _headers(agent_name: str) -> dict:
    return {"X-API-Key": f"bottube_sk_{agent_name}"}


def _login_web(client, agent_name: str) -> None:
    """Attach the web session cookie for ``agent_name`` to ``client``."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        agent_row_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
        ).fetchone()[0]
    with client.session_transaction() as sess:
        sess["agent_id"] = agent_row_id
        sess["user_id"] = agent_row_id
        sess["csrf_token"] = "shared-append-2141-csrf"


def _web_headers() -> dict:
    return {"X-CSRF-Token": "shared-append-2141-csrf"}


def test_shared_helper_reports_outcomes_and_positions(client):
    """The exact sequence named in issue #2141: add, duplicate add, add."""
    owner_id = _insert_agent("shared-owner", 1000.0)
    creator_id = _insert_agent("shared-creator", 1001.0)
    playlist_row_id = _insert_playlist("plshared01", owner_id, "Shared")
    _insert_video("sharedvid01", creator_id, "V1", 1002.0)
    _insert_video("sharedvid02", creator_id, "V2", 1003.0)

    with bottube_server.app.app_context():
        db = bottube_server.get_db()

        first = bottube_server._append_playlist_item(db, playlist_row_id, "sharedvid01")
        duplicate = bottube_server._append_playlist_item(db, playlist_row_id, "sharedvid01")
        second = bottube_server._append_playlist_item(db, playlist_row_id, "sharedvid02")

    assert first == 1
    assert duplicate is None
    assert second == 2


def test_shared_helper_duplicate_leaves_no_extra_row(client):
    owner_id = _insert_agent("shared-owner", 1000.0)
    creator_id = _insert_agent("shared-creator", 1001.0)
    playlist_row_id = _insert_playlist("plshared02", owner_id, "Shared")
    _insert_video("sharedvid11", creator_id, "V1", 1002.0)

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        bottube_server._append_playlist_item(db, playlist_row_id, "sharedvid11")
        bottube_server._append_playlist_item(db, playlist_row_id, "sharedvid11")
        rows = db.execute(
            "SELECT position FROM playlist_items WHERE playlist_id = ?",
            (playlist_row_id,),
        ).fetchall()

    assert [row[0] for row in rows] == [1]


def test_api_route_contract_unchanged(client):
    owner_id = _insert_agent("shared-owner", 1000.0)
    creator_id = _insert_agent("shared-creator", 1001.0)
    _insert_playlist("plshared03", owner_id, "Shared")
    _insert_video("sharedvid21", creator_id, "V1", 1002.0)
    _insert_video("sharedvid22", creator_id, "V2", 1003.0)

    first = client.post(
        "/api/playlists/plshared03/items",
        headers=_headers("shared-owner"),
        json={"video_id": "sharedvid21"},
    )
    duplicate = client.post(
        "/api/playlists/plshared03/items",
        headers=_headers("shared-owner"),
        json={"video_id": "sharedvid21"},
    )
    second = client.post(
        "/api/playlists/plshared03/items",
        headers=_headers("shared-owner"),
        json={"video_id": "sharedvid22"},
    )

    assert first.status_code == 201
    assert first.get_json()["position"] == 1
    assert duplicate.status_code == 409
    assert duplicate.get_json() == {"error": "Video already in playlist"}
    assert second.status_code == 201
    assert second.get_json()["position"] == 2


def test_web_route_contract_unchanged(client):
    owner_id = _insert_agent("shared-owner", 1000.0)
    creator_id = _insert_agent("shared-creator", 1001.0)
    playlist_row_id = _insert_playlist("plshared04", owner_id, "Shared")
    _insert_video("sharedvid31", creator_id, "V1", 1002.0)
    _insert_video("sharedvid32", creator_id, "V2", 1003.0)
    _login_web(client, "shared-owner")

    first = client.post(
        "/playlist/plshared04/add",
        headers=_web_headers(),
        json={"video_id": "sharedvid31"},
    )
    duplicate = client.post(
        "/playlist/plshared04/add",
        headers=_web_headers(),
        json={"video_id": "sharedvid31"},
    )
    second = client.post(
        "/playlist/plshared04/add",
        headers=_web_headers(),
        json={"video_id": "sharedvid32"},
    )

    assert first.status_code == 200, first.get_data(as_text=True)
    assert first.get_json()["ok"] is True
    assert duplicate.status_code == 409
    assert duplicate.get_json() == {"error": "Already in playlist"}
    assert second.status_code == 200

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        rows = db.execute(
            "SELECT video_id, position FROM playlist_items "
            "WHERE playlist_id = ? ORDER BY position",
            (playlist_row_id,),
        ).fetchall()

    assert [(row[0], row[1]) for row in rows] == [
        ("sharedvid31", 1),
        ("sharedvid32", 2),
    ]


def test_api_and_web_routes_share_one_position_sequence(client):
    """API and web appends must not drift into separate position sequences."""
    owner_id = _insert_agent("shared-owner", 1000.0)
    creator_id = _insert_agent("shared-creator", 1001.0)
    playlist_row_id = _insert_playlist("plshared05", owner_id, "Shared")
    for i in range(1, 5):
        _insert_video(f"sharedmix{i:02d}", creator_id, f"V{i}", 1010.0 + i)
    _login_web(client, "shared-owner")

    api_first = client.post(
        "/api/playlists/plshared05/items",
        headers=_headers("shared-owner"),
        json={"video_id": "sharedmix01"},
    )
    web_first = client.post(
        "/playlist/plshared05/add",
        headers=_web_headers(),
        json={"video_id": "sharedmix02"},
    )
    api_second = client.post(
        "/api/playlists/plshared05/items",
        headers=_headers("shared-owner"),
        json={"video_id": "sharedmix03"},
    )
    web_second = client.post(
        "/playlist/plshared05/add",
        headers=_web_headers(),
        json={"video_id": "sharedmix04"},
    )

    assert api_first.status_code == 201
    assert web_first.status_code == 200, web_first.get_data(as_text=True)
    assert api_second.status_code == 201
    assert web_second.status_code == 200

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        rows = db.execute(
            "SELECT video_id, position FROM playlist_items "
            "WHERE playlist_id = ? ORDER BY position",
            (playlist_row_id,),
        ).fetchall()

    assert [(row[0], row[1]) for row in rows] == [
        ("sharedmix01", 1),
        ("sharedmix02", 2),
        ("sharedmix03", 3),
        ("sharedmix04", 4),
    ]
