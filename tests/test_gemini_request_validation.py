# SPDX-License-Identifier: MIT
"""Validation tests for Gemini JSON request parsing."""

import sqlite3

import pytest
import werkzeug
from flask import Flask, g

import gemini_blueprint


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "test"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Build an isolated Flask app around just the Gemini blueprint.

    Registers only `gemini_bp` on a throwaway `Flask(__name__)` (rather than
    importing the full `bottube_server` app) and stubs the actual
    generation calls to always fail the test if reached, so these tests can
    prove validation runs *before* any expensive/paid Gemini API call.
    """
    db_path = tmp_path / "gemini.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL
        );
        INSERT INTO agents (agent_name, api_key)
        VALUES ('gemini_agent', 'bottube_sk_gemini_agent');
        """
    )
    gemini_blueprint.init_gemini_tables(conn)
    conn.commit()
    conn.close()

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.register_blueprint(gemini_blueprint.gemini_bp)

    def _test_get_db():
        """Replace `gemini_blueprint.get_db` with a per-request connection to the test DB.

        The blueprint's real `get_db` opens the production database path;
        swapping it (via `monkeypatch.setattr` below) is what keeps every
        request in these tests confined to `db_path` instead of touching
        whatever database the blueprint module was configured for.
        """
        if "test_db" in g:
            return g.test_db
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        g.test_db = db
        return db

    @app.teardown_appcontext
    def _close_db(_exc):
        """Close the per-request test connection so SQLite file handles don't leak across requests."""
        db = g.pop("test_db", None)
        if db is not None:
            db.close()

    monkeypatch.setattr(gemini_blueprint, "get_db", _test_get_db)
    monkeypatch.setattr(gemini_blueprint, "_HAS_GENAI", True)
    monkeypatch.setattr(gemini_blueprint, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        gemini_blueprint,
        "_generate_image_sync",
        lambda _prompt: pytest.fail("image generation should not run"),
    )
    monkeypatch.setattr(
        gemini_blueprint.threading,
        "Thread",
        lambda *args, **kwargs: pytest.fail("video generation should not start"),
    )
    gemini_blueprint._rate_buckets.clear()
    gemini_blueprint._ip_rate_buckets.clear()

    test_client = app.test_client()
    test_client.db_path = db_path
    return test_client


def _auth_headers():
    """Return the API key header for the single agent seeded by the `client` fixture."""
    return {"X-API-Key": "bottube_sk_gemini_agent"}


def _job_count(db_path):
    """Return how many rows exist in `gemini_jobs`, used to prove rejected requests created none."""
    with sqlite3.connect(str(db_path)) as db:
        return db.execute("SELECT COUNT(*) FROM gemini_jobs").fetchone()[0]


def _insert_jobs(db_path, count):
    """Seed `count` already-completed jobs, oldest first, to test limit/pagination behavior."""
    with sqlite3.connect(str(db_path)) as db:
        for idx in range(count):
            db.execute(
                """
                INSERT INTO gemini_jobs
                    (job_id, agent_id, job_type, model, prompt, status, created_at)
                VALUES (?, 1, 'image', 'gemini', ?, 'completed', ?)
                """,
                (f"job-{idx:03d}", f"prompt {idx}", float(idx)),
            )
        db.commit()


def test_authenticated_video_rejects_non_object_json_without_job(client):
    """A JSON array body must 400 before any job row is created.

    `_job_count == 0` afterward is the load-bearing assertion: it proves
    the rejection happens before the (stubbed-to-fail) generation call, not
    just that the HTTP status looks right.
    """
    resp = client.post(
        "/api/gemini/generate-video",
        json=["not", "an", "object"],
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"
    assert _job_count(client.db_path) == 0


def test_authenticated_video_rejects_non_string_prompt_without_job(client):
    """A list-typed `prompt` must be rejected, not silently stringified into a job."""
    resp = client.post(
        "/api/gemini/generate-video",
        json={"prompt": ["draw this"]},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "prompt must be a string"
    assert _job_count(client.db_path) == 0


def test_authenticated_video_rejects_non_string_negative_prompt_without_job(client):
    """`negative_prompt` needs its own type check even though `prompt` is valid here.

    A validator that only checked `prompt` and forwarded the rest of the
    body unchecked would let a malformed `negative_prompt` reach the
    (stubbed) generation call instead of failing fast with a clear error.
    """
    resp = client.post(
        "/api/gemini/generate-video",
        json={"prompt": "draw this", "negative_prompt": ["bad"]},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "negative_prompt must be a string"
    assert _job_count(client.db_path) == 0


def test_authenticated_image_rejects_non_string_prompt_before_generation(client):
    """The image endpoint enforces the same `prompt` type check as video, independently.

    Video and image are separate routes/handlers; this guards against the
    image path having its own, weaker (or missing) copy of the validation
    the video tests above already cover.
    """
    resp = client.post(
        "/api/gemini/generate-image",
        json={"prompt": {"text": "draw this"}},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "prompt must be a string"
    assert _job_count(client.db_path) == 0


def test_jobs_rejects_malformed_limit(client):
    """A non-numeric `limit` query param must 400 rather than fall back to a default silently."""
    resp = client.get("/api/gemini/jobs?limit=not-an-int", headers=_auth_headers())

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "limit must be an integer"


def test_jobs_clamps_limit(client):
    """`limit` must be clamped into [1, 50], not passed through raw to the SQL query.

    `limit=0` clamping up to 1 and `limit=999` clamping down to 50 (against
    60 seeded jobs) both matter: an un-clamped 0 would return an empty
    result silently, and an un-clamped huge limit would let a caller pull
    the entire job history in one request.
    """
    _insert_jobs(client.db_path, 60)

    resp = client.get("/api/gemini/jobs?limit=0", headers=_auth_headers())
    body = resp.get_json()

    assert resp.status_code == 200
    assert len(body["jobs"]) == 1

    resp = client.get("/api/gemini/jobs?limit=999", headers=_auth_headers())
    body = resp.get_json()

    assert resp.status_code == 200
    assert len(body["jobs"]) == 50


@pytest.mark.parametrize(
    ("path", "payload", "expected_error"),
    [
        ("/api/gemini/free/generate-video", ["bad"], "JSON object required"),
        ("/api/gemini/free/generate-video", {"prompt": ["bad"]}, "prompt must be a string"),
        (
            "/api/gemini/free/generate-video",
            {"prompt": "draw this", "negative_prompt": ["bad"]},
            "negative_prompt must be a string",
        ),
        ("/api/gemini/free/generate-image", ["bad"], "JSON object required"),
        ("/api/gemini/free/generate-image", {"prompt": ["bad"]}, "prompt must be a string"),
    ],
)
def test_free_gemini_routes_reject_malformed_json_without_quota_or_job(
    client, path, payload, expected_error
):
    """Unauthenticated /free/* endpoints must reject bad input before spending IP quota.

    Unlike the authenticated tests above, no `_auth_headers()` is sent here
    -- these routes are rate-limited per IP instead of per API key, so the
    `_ip_rate_buckets == {}` assertion confirms a malformed request doesn't
    consume a free-tier quota slot it never earned by reaching real work.
    """
    resp = client.post(path, json=payload)

    assert resp.status_code == 400
    assert resp.get_json()["error"] == expected_error
    assert _job_count(client.db_path) == 0
    assert gemini_blueprint._ip_rate_buckets == {}
