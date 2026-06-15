# SPDX-License-Identifier: MIT
"""
Regression tests for GET /api/videos/<video_id>/tips pagination OFFSET overflow.

Bug: ``page`` was parsed with ``max(1, request.args.get("page", 1, type=int))``
without an upper bound. An astronomically large ``?page`` made
``offset = (page - 1) * per_page`` exceed SQLite's signed 64-bit INTEGER range,
which raises ``OperationalError`` ("Python int too large to convert to SQLite
INTEGER") on the ``LIMIT ? OFFSET ?`` query and surfaces as an HTTP 500.

Verified on production before the fix (CossKX9jcGF is a real video id):
    GET https://bottube.ai/api/videos/CossKX9jcGF/tips?page=9223372036854775807 -> 500
    GET https://bottube.ai/api/videos/CossKX9jcGF/tips?page=1               -> 200

Fix: reject pages whose offset would overflow SQLite with a clean 400, while
leaving normal (even large but safe) pagination untouched.
"""
import time

_SQLITE_MAX_SIGNED_INT = 2 ** 63 - 1
_VIDEO_ID = "tips_overflow_video_1102"


def _make_video(app):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """INSERT INTO agents (agent_name, display_name, api_key, created_at)
               VALUES (?, ?, ?, ?)""",
            ("tips-overflow-owner", "Tips Overflow Owner", "tips-overflow-key", time.time()),
        )
        agent_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            ("tips-overflow-owner",),
        ).fetchone()["id"]
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (_VIDEO_ID, agent_id, "Overflow video", "overflow.mp4", time.time()),
        )
        db.commit()


def test_tips_max_int_page_returns_400_not_500(app, client):
    """A page at SQLite's 64-bit ceiling must 400 cleanly, never 500."""
    _make_video(app)
    resp = client.get(f"/api/videos/{_VIDEO_ID}/tips?page={_SQLITE_MAX_SIGNED_INT}")
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}"
    assert "page" in resp.get_json()["error"]


def test_tips_overflowing_page_returns_400(app, client):
    """A page beyond 64 bits (offset overflow) must 400, never 500."""
    _make_video(app)
    resp = client.get(f"/api/videos/{_VIDEO_ID}/tips?page=99999999999999999999")
    assert resp.status_code == 400


def test_tips_normal_page_still_ok(app, client):
    """The fix must not regress ordinary pagination."""
    _make_video(app)
    resp = client.get(f"/api/videos/{_VIDEO_ID}/tips?page=1")
    assert resp.status_code == 200
    assert resp.get_json()["video_id"] == _VIDEO_ID


def test_tips_large_but_safe_page_ok(app, client):
    """A large page whose offset stays within 64 bits returns 200 (empty page)."""
    # offset = (10**9 - 1) * 10 ~= 1e10, well inside SQLite's signed 64-bit range.
    _make_video(app)
    resp = client.get(f"/api/videos/{_VIDEO_ID}/tips?page=1000000000")
    assert resp.status_code == 200
