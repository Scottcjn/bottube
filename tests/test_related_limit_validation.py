# SPDX-License-Identifier: MIT
"""
Regression tests for GET /api/videos/<video_id>/related limit validation.

Bug: the limit query param was parsed with
min(20, max(1, request.args.get("limit", 8, type=int))) which silently
coerces non-integer / negative / zero values to the default via Flask's
type=int coercion. No 400 was ever returned.

Fix: explicit validation that returns JSON 400 for malformed input.
"""
import time

_VIDEO_ID = "related_limit_test_vid"


def _make_video(app):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """INSERT INTO agents (agent_name, display_name, api_key, created_at)
               VALUES (?, ?, ?, ?)""",
            ("related-limit-owner", "Related Limit Owner", "rlt-key", time.time()),
        )
        agent_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            ("related-limit-owner",),
        ).fetchone()["id"]
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (_VIDEO_ID, agent_id, "Related limit test", "related.mp4", time.time()),
        )
        db.commit()


def test_related_rejects_non_integer_limit(app, client):
    _make_video(app)
    resp = client.get(f"/api/videos/{_VIDEO_ID}/related?limit=abc")
    assert resp.status_code == 400
    assert "limit" in resp.get_json()["error"]


def test_related_rejects_negative_limit(app, client):
    _make_video(app)
    resp = client.get(f"/api/videos/{_VIDEO_ID}/related?limit=-5")
    assert resp.status_code == 400


def test_related_rejects_zero_limit(app, client):
    _make_video(app)
    resp = client.get(f"/api/videos/{_VIDEO_ID}/related?limit=0")
    assert resp.status_code == 400


def test_related_rejects_oversized_limit(app, client):
    _make_video(app)
    resp = client.get(f"/api/videos/{_VIDEO_ID}/related?limit=999")
    assert resp.status_code == 400


def test_related_accepts_valid_limit(app, client):
    _make_video(app)
    resp = client.get(f"/api/videos/{_VIDEO_ID}/related?limit=5")
    assert resp.status_code == 200


def test_related_accepts_default_limit(app, client):
    _make_video(app)
    resp = client.get(f"/api/videos/{_VIDEO_ID}/related")
    assert resp.status_code == 200
