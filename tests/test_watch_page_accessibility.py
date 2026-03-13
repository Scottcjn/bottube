import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_watch_accessibility_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_watch_accessibility_bootstrap.db")

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
    Path(bootstrap_path).unlink(missing_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_watch_accessibility.db"
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
            VALUES (?, ?, ?, '', '', '', 0, ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, 1.0, 1.0),
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
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, "Accessibility Video", f"{video_id}.mp4", 1.0),
        )
        db.commit()


def test_watch_page_renders_keyboard_shortcuts_and_accessibility_regions(client):
    agent_id = _insert_agent("shortcutbot", "bottube_sk_shortcutbot")
    _insert_video(agent_id, "watcha11y01")

    resp = client.get("/watch/watcha11y01")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'id="player-region"' in html
    assert 'role="region"' in html
    assert 'aria-label="Video player"' in html
    assert 'id="comments-region"' in html
    assert 'aria-label="Comments section"' in html
    assert 'id="recommendations-region"' in html
    assert 'aria-label="Up next videos"' in html
    assert 'id="shortcut-help-btn"' in html
    assert 'id="shortcut-help-modal"' in html
    assert 'aria-keyshortcuts="Space,K,J,L,F,M,ArrowUp,ArrowDown,ArrowLeft,ArrowRight,Escape,Shift+Slash"' in html
    assert 'function openShortcutHelp()' in html
    assert "document.addEventListener('keydown'" in html
    assert "Shortcuts are disabled while typing in comment" in html
    assert "function isShortcutBypassTarget(target)" in html

    keydown_block_start = html.index("document.addEventListener('keydown'")
    keydown_block = html[keydown_block_start:]
    assert keydown_block.index("isShortcutBypassTarget(event.target)") < keydown_block.index("openShortcutHelp();")
