# SPDX-License-Identifier: MIT
"""
Regression tests for /xrpc/feed.firehose `limit` query validation.

Bug: Bottube #1447 (`/xrpc/feed.firehose silently accepts malformed limit
query values`).

The public signed firehose endpoint currently parses `limit` with
`max(1, min(200, int(request.args.get("limit", 100))))` inside a
try/except that silently coerces malformed input back to the default.
That breaks deterministic pagination for federation/feed consumers:
`limit=abc` becomes 100, `limit=0` is clamped up to 1, `limit=201` is
clamped down to 200, and there is no way for a client to detect the
malformed input.

Fix: switch the `limit` parse to the existing `_parse_positive_int_query`
helper that already gates the other public Bottube routes. Malformed
values now produce JSON `400 {"error": "limit must be an integer"}` (or
out-of-range variant), matching the contract established by PR #1397
(feed/videos) and PR #1402 (feed).
"""

import pytest

import bottube_server


@pytest.fixture
def firehose_client(tmp_path):
    """Fresh in-memory-style Bottube app for the firehose route.

    Uses a temp dir for the database so video_provenance and the other
    late-bound tables can be created cleanly inside the test process.
    """
    import importlib
    import os
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Force a clean re-import so DB_PATH/VIDEO_DIR pick up the temp dir.
        for mod_name in list(sys.modules.keys()):
            if mod_name == "bottube_server" or mod_name.startswith("bottube_server."):
                del sys.modules[mod_name]

        prev_base_dir = os.environ.get("BOTTUBE_BASE_DIR")
        os.environ["BOTTUBE_BASE_DIR"] = tmpdir

        sys.path.insert(0, str(tmp_path))
        import bottube_server  # noqa: F401  re-import

        flask_app = bottube_server.app
        flask_app.config["TESTING"] = True
        flask_app.config["SECRET_KEY"] = "test-secret-key"

        with flask_app.app_context():
            bottube_server.init_db()
            # Phase-11 firehose depends on video_provenance. Make sure the
            # bootstrap schema is rebuilt against the fresh DB.
            bottube_server._PROVENANCE_SCHEMA_READY = False
            bottube_server._ensure_provenance_schema()

        try:
            yield flask_app.test_client()
        finally:
            if prev_base_dir is None:
                os.environ.pop("BOTTUBE_BASE_DIR", None)
            else:
                os.environ["BOTTUBE_BASE_DIR"] = prev_base_dir


def test_firehose_rejects_non_integer_limit(firehose_client):
    """Non-numeric `limit` must return JSON 400, not silently fall back to 100."""
    resp = firehose_client.get("/xrpc/feed.firehose?limit=abc")
    assert resp.status_code == 400
    assert resp.content_type.startswith("application/json")
    data = resp.get_json()
    assert "limit" in data["error"]
    assert "integer" in data["error"]


def test_firehose_rejects_zero_limit(firehose_client):
    """`limit=0` is below the documented min of 1; must return 400."""
    resp = firehose_client.get("/xrpc/feed.firehose?limit=0")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "limit" in data["error"]
    assert ">=" in data["error"]


def test_firehose_rejects_negative_limit(firehose_client):
    resp = firehose_client.get("/xrpc/feed.firehose?limit=-5")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "limit" in data["error"]
    assert ">=" in data["error"]


def test_firehose_rejects_oversized_limit(firehose_client):
    """`limit=201` is above the documented max of 200; must return 400."""
    resp = firehose_client.get("/xrpc/feed.firehose?limit=201")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "limit" in data["error"]
    assert "<=" in data["error"]


def test_firehose_rejects_floating_point_limit(firehose_client):
    """`limit=3.5` is not an integer; must return 400 (not silently truncate)."""
    resp = firehose_client.get("/xrpc/feed.firehose?limit=3.5")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "limit" in data["error"]


def test_firehose_accepts_default_limit(firehose_client):
    """No `limit` param: route must accept the default of 100 and return JSON 200."""
    resp = firehose_client.get("/xrpc/feed.firehose")
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")


def test_firehose_accepts_boundary_limit_low(firehose_client):
    """`limit=1` is the documented min boundary; must succeed with 200."""
    resp = firehose_client.get("/xrpc/feed.firehose?limit=1")
    assert resp.status_code == 200


def test_firehose_accepts_boundary_limit_high(firehose_client):
    """`limit=200` is the documented max boundary; must succeed with 200."""
    resp = firehose_client.get("/xrpc/feed.firehose?limit=200")
    assert resp.status_code == 200


def test_firehose_accepts_numeric_string_limit(firehose_client):
    """`limit=50` (string-typed int) must succeed (Flask parses as int)."""
    resp = firehose_client.get("/xrpc/feed.firehose?limit=50")
    assert resp.status_code == 200


def test_firehose_invalid_cursor_still_rejected(firehose_client):
    """The pre-existing `cursor` validation must not regress."""
    resp = firehose_client.get("/xrpc/feed.firehose?cursor=not-a-cursor")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "cursor" in data["error"]


def test_firehose_valid_cursor_with_invalid_limit(firehose_client):
    """When both are present, malformed `limit` is reported first (limit is parsed
    before cursor in the handler)."""
    resp = firehose_client.get("/xrpc/feed.firehose?cursor=1700000000:42&limit=abc")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "limit" in data["error"]