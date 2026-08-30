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
    """Gemini app with an isolated test DB, wired get_db, and a seeded agent."""
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
        """Per-test SQLite connection swapped in for the blueprint's get_db."""
        if "test_db" in g:
            return g.test_db
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        g.test_db = db
        return db

    @app.teardown_appcontext
    def _close_db(_exc):
        """Close the per-request test connection on teardown."""
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
    """X-API-Key headers for the seeded test agent."""
    return {"X-API-Key": "bottube_sk_gemini_agent"}


def _job_count(db_path):
    """Row count of gemini_jobs, to assert no job was created."""
    with sqlite3.connect(str(db_path)) as db:
        return db.execute("SELECT COUNT(*) FROM gemini_jobs").fetchone()[0]


def _insert_jobs(db_path, count):
    """Insert N gemini_jobs rows directly."""
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
    """A non-object generate-video body is rejected with 400 and no job is created."""
    resp = client.post(
        "/api/gemini/generate-video",
        json=["not", "an", "object"],
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"
    assert _job_count(client.db_path) == 0


def test_authenticated_video_rejects_non_string_prompt_without_job(client):
    """A non-string video prompt is rejected with 400 and no job is created."""
    resp = client.post(
        "/api/gemini/generate-video",
        json={"prompt": ["draw this"]},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "prompt must be a string"
    assert _job_count(client.db_path) == 0


def test_authenticated_video_rejects_non_string_negative_prompt_without_job(client):
    """A non-string negative_prompt is rejected with 400 and no job is created."""
    resp = client.post(
        "/api/gemini/generate-video",
        json={"prompt": "draw this", "negative_prompt": ["bad"]},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "negative_prompt must be a string"
    assert _job_count(client.db_path) == 0


def test_authenticated_image_rejects_non_string_prompt_before_generation(client):
    """A non-string image prompt is rejected before any generation work."""
    resp = client.post(
        "/api/gemini/generate-image",
        json={"prompt": {"text": "draw this"}},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "prompt must be a string"
    assert _job_count(client.db_path) == 0


def test_jobs_rejects_malformed_limit(client):
    """A non-integer jobs limit is rejected with 400."""
    resp = client.get("/api/gemini/jobs?limit=not-an-int", headers=_auth_headers())

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "limit must be an integer"


def test_jobs_clamps_limit(client):
    """A zero/out-of-range jobs limit is clamped to a safe bound."""
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
    """Free Gemini routes reject malformed JSON without touching quota or creating jobs."""
    resp = client.post(path, json=payload)

    assert resp.status_code == 400
    assert resp.get_json()["error"] == expected_error
    assert _job_count(client.db_path) == 0
    assert gemini_blueprint._ip_rate_buckets == {}
