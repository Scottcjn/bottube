"""Regression: POST /api/gpu/jobs/fail must not reopen completed jobs (issue #2167)."""
import pytest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bottube_server import app as flask_app, init_db
from gpu_marketplace import init_gpu_db, get_db


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True)
    with flask_app.app_context():
        init_db()
        init_gpu_db(":memory:")
        db = get_db()
        now = time.time()
        db.execute(
            "INSERT OR REPLACE INTO agents (id, agent_name, display_name, api_key, is_banned, created_at) VALUES (1, 'test-agent', 'Test Agent', 'test-key', 0, ?)",
            (now,),
        )
        db.commit()
        yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _seed_provider(db, agent_id=1, provider_id="prov-1"):
    db.execute(
        "INSERT OR REPLACE INTO gpu_providers (id, agent_id, gpu_model, gpu_vram_gb, price_per_min, status, created_at) VALUES (?, ?, 'RTX 3080', 10, 0.1, 'online', 1700000000)",
        (provider_id, agent_id),
    )
    db.commit()
    return provider_id


def _seed_job(db, job_id="job-1", provider_id="prov-1", status="running"):
    db.execute(
        """INSERT OR REPLACE INTO gpu_jobs
           (id, provider_id, requester_id, job_type, job_params, status, rtc_escrowed, created_at)
           VALUES (?, ?, 1, 'render', '{}', ?, 1.0, 1700000000)""",
        (job_id, provider_id, status),
    )
    db.commit()


def test_fail_rejects_completed_job(client, app):
    with app.app_context():
        db = get_db()
        pid = _seed_provider(db)
        _seed_job(db, status="completed")

    resp = client.post(
        "/api/gpu/jobs/fail",
        json={"provider_id": pid, "job_id": "job-1", "error_message": "boom"},
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 409
    data = resp.get_json()
    assert "cannot be failed" in data["error"].lower() or "status" in data["error"].lower()

    with app.app_context():
        row = get_db().execute(
            "SELECT status FROM gpu_jobs WHERE id = ?", ("job-1",)
        ).fetchone()
    assert row[0] == "completed"


def test_fail_concurrent_release_one_winner(client, app):
    with app.app_context():
        db = get_db()
        pid = _seed_provider(db)
        _seed_job(db, status="running")

    r1 = client.post(
        "/api/gpu/jobs/fail",
        json={"provider_id": pid, "job_id": "job-1", "error_message": "e1"},
        headers={"X-API-Key": "test-key"},
    )
    # After first release, job is pending and provider_id is NULL.
    # Second call with same provider_id fails ownership check (403) because
    # the job no longer belongs to that provider. This is correct behavior:
    # only the owning provider can release, and once released it's gone.
    r2 = client.post(
        "/api/gpu/jobs/fail",
        json={"provider_id": pid, "job_id": "job-1", "error_message": "e2"},
        headers={"X-API-Key": "test-key"},
    )

    assert r1.status_code == 200
    assert r2.status_code in (403, 409)

    with app.app_context():
        rows = get_db().execute(
            "SELECT status, error_message FROM gpu_jobs WHERE id = ?", ("job-1",)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "pending"
    assert rows[0][1] == "e1"
