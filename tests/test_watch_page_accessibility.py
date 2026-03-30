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
    assert 'aria-keyshortcuts="Space,K,J,L,F,M,C,ArrowUp,ArrowDown,ArrowLeft,ArrowRight,Escape,Shift+Slash"' in html
    assert 'function openShortcutHelp()' in html
    assert "document.addEventListener('keydown'" in html
    assert "Shortcuts are disabled while typing in comment" in html
    assert "function isShortcutBypassTarget(target)" in html
    assert 'toggleCaptions' in html
    assert 'Toggle captions' in html

    keydown_block_start = html.index("document.addEventListener('keydown'")
    keydown_block = html[keydown_block_start:]
    assert keydown_block.index("isShortcutBypassTarget(event.target)") < keydown_block.index("openShortcutHelp();")


def test_watch_page_unmute_button_keyboard_accessible(client):
    """Test that the unmute button is keyboard accessible with proper ARIA (Issue #420)."""
    agent_id = _insert_agent("unmutebot", "bottube_sk_unmutebot")
    _insert_video(agent_id, "watcha11y02")

    resp = client.get("/watch/watcha11y02")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Unmute button should have proper ARIA label
    assert 'id="unmute-btn"' in html
    assert 'aria-label="Unmute video audio"' in html
    assert 'type="button"' in html
    # Should have keyboard event handler
    assert 'onkeydown="handleUnmuteKeydown(event)"' in html
    # Should have click handler
    assert 'onclick="unmuteVideo()"' in html
    # Should have the JavaScript handler function
    assert 'function handleUnmuteKeydown(event)' in html
    assert "event.key === 'Enter' || event.key === ' '" in html


def test_watch_page_player_state_live_region(client):
    """Test that player state changes are announced via ARIA live region (Issue #420)."""
    agent_id = _insert_agent("statebot", "bottube_sk_statebot")
    _insert_video(agent_id, "watcha11y03")

    resp = client.get("/watch/watcha11y03")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Live region for player state announcements
    assert 'id="player-state"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'aria-atomic="true"' in html
    # announcePlayerState function should exist
    assert 'function announcePlayerState(message)' in html
    assert "liveRegion.textContent = message" in html


def test_watch_page_keyboard_shortcuts_announce_state(client):
    """Test that keyboard shortcuts announce state changes for accessibility (Issue #420)."""
    agent_id = _insert_agent("announcebot", "bottube_sk_announcebot")
    _insert_video(agent_id, "watcha11y04")

    resp = client.get("/watch/watcha11y04")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Toggle playback should announce state
    assert "announcePlayerState('Playing')" in html
    assert "announcePlayerState('Paused')" in html
    # Seek should announce direction
    assert "announcePlayerState('Seeked" in html
    # Volume should announce percentage
    assert "announcePlayerState('Volume" in html
    # Mute should announce state
    assert "announcePlayerState('Muted')" in html or "announcePlayerState(video.muted ? 'Muted' : 'Unmuted')" in html
    # Fullscreen should announce state
    assert "announcePlayerState('Exited fullscreen')" in html
    assert "announcePlayerState('Entered fullscreen')" in html
    # Replay should announce action
    assert "announcePlayerState('Replaying video')" in html


def test_watch_page_visible_focus_styles(client):
    """Test that visible focus styles are defined for keyboard navigation (Issue #420)."""
    agent_id = _insert_agent("focusbot", "bottube_sk_focusbot")
    _insert_video(agent_id, "watcha11y05")

    resp = client.get("/watch/watcha11y05")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Focus styles for unmute button
    assert '.unmute-overlay:focus-visible' in html
    # Focus styles for end-screen buttons
    assert '.es-share-btn:focus-visible' in html
    assert '.es-replay:focus-visible' in html
    # Focus-within for player region
    assert '.video-player-region:focus-within' in html
    # General focus-visible styles
    assert ':focus-visible' in html
    assert 'outline' in html


def test_watch_page_captions_announce_state(client):
    """Test that captions toggle announces state change (Issue #420)."""
    agent_id = _insert_agent("captionbot", "bottube_sk_captionbot")
    _insert_video(agent_id, "watcha11y06")

    resp = client.get("/watch/watcha11y06")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Captions toggle should announce state
    assert "announcePlayerState('Captions enabled')" in html or "announcePlayerState(captionsEnabled ? 'Captions enabled' : 'Captions disabled')" in html
    # Should handle no captions case
    assert "announcePlayerState('No captions available')" in html
