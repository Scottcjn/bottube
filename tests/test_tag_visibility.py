import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "BOTTUBE_DB_PATH",
    "/tmp/bottube_test_tag_visibility_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_tag_visibility_bootstrap.db",
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
    db_path = tmp_path / "bottube_tag_visibility_test.db"
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
    tags: list[str],
    created_at: float,
    *,
    is_removed: int = 0,
) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, tags, created_at,
                 views, is_removed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                agent_id,
                title,
                f"{video_id}.mp4",
                json.dumps(tags),
                created_at,
                int(created_at),
                is_removed,
            ),
        )
        db.commit()


def test_api_tags_ignores_banned_owner_and_removed_videos(client):
    visible_id = _insert_agent("visible-agent", 1000.0)
    banned_id = _insert_agent("banned-agent", 1001.0, is_banned=1)
    _insert_video(
        "visiblevid01",
        visible_id,
        "Visible Tag Video",
        ["rust", "ai"],
        1002.0,
    )
    _insert_video(
        "bannedvid01",
        banned_id,
        "Banned Tag Video",
        ["rust"],
        1003.0,
    )
    _insert_video(
        "removedvid01",
        visible_id,
        "Removed Tag Video",
        ["rust"],
        1004.0,
        is_removed=1,
    )

    resp = client.get("/api/tags")

    assert resp.status_code == 200
    tags = {row["tag"]: row["count"] for row in resp.get_json()["tags"]}
    assert tags["rust"] == 1
    assert tags["ai"] == 1


def test_tag_page_hides_banned_owner_videos(client):
    visible_id = _insert_agent("visible-agent", 1000.0)
    banned_id = _insert_agent("banned-agent", 1001.0, is_banned=1)
    _insert_video(
        "visiblevid01",
        visible_id,
        "Visible Tag Video",
        ["rust"],
        1002.0,
    )
    _insert_video(
        "bannedvid01",
        banned_id,
        "Banned Tag Video",
        ["rust"],
        1003.0,
    )

    resp = client.get("/tag/rust")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Visible Tag Video" in body
    assert "Banned Tag Video" not in body
