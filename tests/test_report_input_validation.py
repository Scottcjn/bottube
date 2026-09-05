# SPDX-License-Identifier: MIT
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
    "/tmp/bottube_test_report_input_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_report_input_bootstrap.db",
)

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    """Redirect the hardcoded production DB path to the test bootstrap path.

    Import-time code opens `/root/bottube/bottube.db` before the `client`
    fixture can monkeypatch `DB_PATH`, so without this shim collecting
    this module would touch production report/comment data.
    """
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages  # noqa: E402


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    """Force paypal_packages' schema init onto the test bootstrap DB, not the real one."""
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server  # noqa: E402

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Yield a Flask test client on an isolated, per-test SQLite database."""
    db_path = tmp_path / "bottube_report_input_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str) -> int:
    """Insert a minimal agent row directly and return its id.

    Used to seed both the video/comment owner and the reporter, since
    report validation itself doesn't depend on how the accounts were
    created.
    """
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url,
                 created_at, last_active)
            VALUES (?, ?, ?, '', '', ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, 1.0, 1.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(agent_id: int, video_id: str) -> None:
    """Seed a video owned by `agent_id` so `/api/videos/<id>/report` has a target to reject or accept a report against."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, f"Video {video_id}", f"{video_id}.mp4", 2.0),
        )
        db.commit()


def _insert_comment(agent_id: int, video_id: str, content: str) -> int:
    """Seed a comment and return its id, so `/api/comments/<id>/report` has a target."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, agent_id, content, 3.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _report_count() -> int:
    """Return how many rows exist in `reports`, used to prove a rejected request inserted nothing."""
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        return int(db.execute("SELECT COUNT(*) FROM reports").fetchone()[0])


def test_report_insert_is_atomic_per_reporter_and_target(client):
    owner_id = _insert_agent("atomicowner", "bottube_sk_atomicowner")
    reporter_id = _insert_agent("atomicreporter", "bottube_sk_atomicreporter")
    _insert_video(owner_id, "atomicreport01A")
    comment_id = _insert_comment(owner_id, "atomicreport01A", "report target")

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        first_video = bottube_server._insert_report_once(
            db,
            reporter_id=reporter_id,
            video_id="atomicreport01A",
            reason="spam",
            details="first",
            created_at=10.0,
        )
        duplicate_video = bottube_server._insert_report_once(
            db,
            reporter_id=reporter_id,
            video_id="atomicreport01A",
            reason="harassment",
            details="retry",
            created_at=11.0,
        )
        first_comment = bottube_server._insert_report_once(
            db,
            reporter_id=reporter_id,
            comment_id=comment_id,
            reason="spam",
            details="first",
            created_at=12.0,
        )
        duplicate_comment = bottube_server._insert_report_once(
            db,
            reporter_id=reporter_id,
            comment_id=comment_id,
            reason="harassment",
            details="retry",
            created_at=13.0,
        )
        db.commit()
        rows = db.execute(
            "SELECT video_id, comment_id, reason FROM reports ORDER BY id"
        ).fetchall()

    assert (first_video, duplicate_video, first_comment, duplicate_comment) == (
        True,
        False,
        True,
        False,
    )
    assert [(row["video_id"], row["comment_id"], row["reason"]) for row in rows] == [
        ("atomicreport01A", None, "spam"),
        (None, comment_id, "spam"),
    ]


def test_report_routes_preserve_duplicate_conflicts(client):
    owner_id = _insert_agent("routeowner", "bottube_sk_routeowner")
    _insert_agent("routereporter", "bottube_sk_routereporter")
    _insert_video(owner_id, "routereport01A")
    comment_id = _insert_comment(owner_id, "routereport01A", "report target")
    headers = {"X-API-Key": "bottube_sk_routereporter"}

    first_video = client.post(
        "/api/videos/routereport01A/report",
        headers=headers,
        json={"reason": "spam"},
    )
    duplicate_video = client.post(
        "/api/videos/routereport01A/report",
        headers=headers,
        json={"reason": "spam"},
    )
    first_comment = client.post(
        f"/api/comments/{comment_id}/report",
        headers=headers,
        json={"reason": "spam"},
    )
    duplicate_comment = client.post(
        f"/api/comments/{comment_id}/report",
        headers=headers,
        json={"reason": "spam"},
    )

    assert first_video.status_code == 200
    assert duplicate_video.status_code == 409
    assert duplicate_video.get_json() == {"error": "You have already reported this video"}
    assert first_comment.status_code == 200
    assert duplicate_comment.status_code == 409
    assert duplicate_comment.get_json() == {"error": "You have already reported this comment"}
    assert _report_count() == 2


def test_video_report_null_reason_uses_existing_invalid_reason_error(client):
    """`reason: null` must fail the same "Invalid reason" check as an unrecognized reason string, not a separate null-check path.

    Proves `null` doesn't get special-cased into passing through or into a
    different (weaker) error message than a plain bad `reason` value would get.
    """
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo01A")

    resp = client.post(
        "/api/videos/ownervideo01A/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json={"reason": None},
    )

    assert resp.status_code == 400
    assert "Invalid reason" in resp.get_json()["error"]
    assert _report_count() == 0


def test_video_report_rejects_non_string_details_without_insert(client):
    """A dict-typed `details` on a video report must 400 with a specific message and write nothing.

    `reason` here is valid ("spam"), isolating the check to `details`
    alone -- proves the two fields are validated independently rather
    than one bad field's error masking a check on the other.
    """
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo01A")

    resp = client.post(
        "/api/videos/ownervideo01A/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json={"reason": "spam", "details": {"text": "bad"}},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "details must be a string"}
    assert _report_count() == 0


def test_comment_report_rejects_non_string_reason_without_insert(client):
    """A list-typed `reason` on a comment report must 400 and insert nothing, mirroring the video-report reason check."""
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo01A")
    comment_id = _insert_comment(owner_id, "ownervideo01A", "spammy")

    resp = client.post(
        f"/api/comments/{comment_id}/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json={"reason": ["spam"], "details": "bad comment"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "reason must be a string"}
    assert _report_count() == 0


def test_comment_report_rejects_non_object_json(client):
    """A JSON array body to /comments/<id>/report must 400 with "JSON body must be an object" and write nothing."""
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo01A")
    comment_id = _insert_comment(owner_id, "ownervideo01A", "spammy")

    resp = client.post(
        f"/api/comments/{comment_id}/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json=["not", "an", "object"],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    assert _report_count() == 0


def test_video_report_rejects_falsy_non_object_json(client):
    """An empty JSON array (`[]`, which is falsy in Python) must still be rejected as "not an object", not treated as "no body"."""
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo02A")

    resp = client.post(
        "/api/videos/ownervideo02A/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json=[],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    assert _report_count() == 0


def test_comment_report_rejects_falsy_non_object_json(client):
    """The same falsy-empty-array case as the video-report test above, but for the comment-report endpoint.

    A validator using `if not body:` to mean "body missing" would wrongly
    let `[]` fall through as "no body provided" instead of "wrong type" --
    covering both endpoints catches this if only one of the two handlers
    shares that bug.
    """
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo03A")
    comment_id = _insert_comment(owner_id, "ownervideo03A", "spammy")

    resp = client.post(
        f"/api/comments/{comment_id}/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json=[],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
    assert _report_count() == 0


def test_video_report_accepts_null_details_as_empty(client):
    """`details: null` must succeed (unlike `reason: null`) since details is genuinely optional.

    Paired with `test_video_report_null_reason_...` above: `null` is
    rejected for the required `reason` field but accepted for the
    optional `details` field, proving the two aren't validated by one
    blanket "no nulls" rule.
    """
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    _insert_agent("reporter", "bottube_sk_reporter")
    _insert_video(owner_id, "ownervideo01A")

    resp = client.post(
        "/api/videos/ownervideo01A/report",
        headers={"X-API-Key": "bottube_sk_reporter"},
        json={"reason": "spam", "details": None},
    )

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert _report_count() == 1
