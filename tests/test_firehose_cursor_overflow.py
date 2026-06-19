# SPDX-License-Identifier: MIT
"""
Regression tests for GET /xrpc/feed.firehose cursor 64-bit overflow.

Bug: the firehose cursor has the form ``<created_at_ms>:<rowid>`` and both
segments were parsed with ``int(...)`` without any upper bound. The second
segment is bound directly as a SQLite INTEGER parameter (``v.id > ?``), so a
value above SQLite's signed 64-bit ceiling raises ``OverflowError`` ("Python
int too large to convert to SQLite INTEGER") inside the driver and surfaces as
an HTTP 500 instead of a deterministic validation error.

Verified on production before the fix:
    GET https://bottube.ai/xrpc/feed.firehose?cursor=0:99999999999999999999999999 -> 500
    GET https://bottube.ai/xrpc/feed.firehose?cursor=0:1                           -> 200

The endpoint already rejects structurally invalid cursors with HTTP 400
("invalid cursor"); this extends the same treatment to out-of-range segments.
"""

_SQLITE_MAX_INT64 = (1 << 63) - 1


def _ensure_firehose_schema(app):
    """The firehose query LEFT JOINs video_provenance, whose schema is created
    lazily by the upload path rather than init_db(). Materialize it so the
    success-path assertions exercise the real query."""
    import bottube_server

    with app.app_context():
        bottube_server._ensure_provenance_schema()


def test_firehose_overflowing_rowid_returns_400_not_500(app, client):
    """A cursor rowid beyond 64 bits must 400 cleanly, never 500.

    This is the production-confirmed crash: the rowid segment is bound as a
    SQLite INTEGER (``v.id > ?``), so an out-of-range value raises
    ``OverflowError`` on the original code -> HTTP 500.
    """
    _ensure_firehose_schema(app)
    resp = client.get("/xrpc/feed.firehose?cursor=0:99999999999999999999999999")
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}"
    assert "cursor" in resp.get_json()["error"]


def test_firehose_overflowing_ms_returns_400(app, client):
    """The timestamp segment is range-checked too, for consistency.

    The ``ms`` segment is divided to a float before binding, so on the
    original code an out-of-range value was silently accepted (200) rather
    than crashing; the fix rejects both segments uniformly.
    """
    _ensure_firehose_schema(app)
    huge = _SQLITE_MAX_INT64 + 1
    resp = client.get(f"/xrpc/feed.firehose?cursor={huge}:1")
    assert resp.status_code == 400


def test_firehose_no_cursor_still_ok(app, client):
    """The fix must not regress the default (cursorless) firehose read."""
    _ensure_firehose_schema(app)
    resp = client.get("/xrpc/feed.firehose?limit=2")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_firehose_normal_cursor_still_ok(app, client):
    """A well-formed in-range cursor returns 200 (empty page on a fresh DB)."""
    _ensure_firehose_schema(app)
    resp = client.get("/xrpc/feed.firehose?cursor=0:1&limit=2")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_firehose_malformed_cursor_still_400(client):
    """A structurally invalid cursor keeps returning the existing 400."""
    resp = client.get("/xrpc/feed.firehose?cursor=notacursor")
    assert resp.status_code == 400
