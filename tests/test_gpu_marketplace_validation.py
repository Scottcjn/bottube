# SPDX-License-Identifier: MIT
"""Regression tests for GPU marketplace JSON request-body validation.

Before this fix the POST handlers parsed the body with ``request.get_json()
or {}``. A non-empty body that is valid JSON but *not* an object (a list,
string or number) is truthy, so ``or {}`` does not replace it and the next
``data.get(...)`` raised ``AttributeError`` -> HTTP 500. ``/jobs/submit`` had a
second 500: a non-numeric ``estimated_mins``/``max_price_per_min`` made
``float(...)`` raise ``ValueError``. Both should be clean 400s instead.
"""
import sqlite3

import pytest
import werkzeug
from flask import Flask

from gpu_marketplace import gpu_bp, init_gpu_tables


@pytest.fixture()
def client(monkeypatch, tmp_path):
    if not hasattr(werkzeug, "__version__"):
        monkeypatch.setattr(werkzeug, "__version__", "test", raising=False)

    db_path = tmp_path / "bottube_gpu.db"
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            display_name TEXT,
            api_key TEXT UNIQUE NOT NULL,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            last_active REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE balances (
            miner_id TEXT PRIMARY KEY,
            amount_i64 INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO agents (agent_name, display_name, api_key, last_active)
        VALUES ('gpu_agent', 'GPU Agent', 'bottube_sk_gpu_agent', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO balances (miner_id, amount_i64)
        VALUES ('gpu_agent', 1000000)
        """
    )
    conn.commit()
    conn.close()
    init_gpu_tables(str(db_path))

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(gpu_bp)

    yield app.test_client()


AUTH = {"X-API-Key": "bottube_sk_gpu_agent"}

POST_ROUTES = [
    "/api/gpu/providers/register",
    "/api/gpu/providers/heartbeat",
    "/api/gpu/jobs/submit",
    "/api/gpu/jobs/claim",
    "/api/gpu/jobs/start",
    "/api/gpu/jobs/complete",
    "/api/gpu/jobs/fail",
]


@pytest.mark.parametrize("route", POST_ROUTES)
@pytest.mark.parametrize("body", [["not", "an", "object"], "a-string", 123])
def test_non_object_json_rejected_with_400(client, route, body):
    resp = client.post(route, headers=AUTH, json=body)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON object required"}


def test_empty_body_still_hits_field_validation(client):
    # Empty body must keep the previous behaviour: defaults applied, then the
    # existing per-field 400 (not a 500, not the new "JSON object required").
    resp = client.post("/api/gpu/providers/register", headers=AUTH)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "gpu_model required"}


def test_valid_object_still_succeeds(client):
    resp = client.post(
        "/api/gpu/providers/register",
        headers=AUTH,
        json={"gpu_model": "RTX 3080", "gpu_vram_gb": 10},
    )

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_submit_job_non_numeric_estimated_mins_rejected(client):
    resp = client.post(
        "/api/gpu/jobs/submit",
        headers=AUTH,
        json={"job_type": "video_render", "estimated_mins": "abc"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Numeric value required"}


def test_submit_job_non_numeric_max_price_rejected(client):
    resp = client.post(
        "/api/gpu/jobs/submit",
        headers=AUTH,
        json={
            "job_type": "video_render",
            "estimated_mins": 5,
            "max_price_per_min": "free",
        },
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Numeric value required"}

def _setup_provider_and_job(client):
    reg_resp = client.post(
        "/api/gpu/providers/register",
        headers=AUTH,
        json={"gpu_model": "RTX 4090", "gpu_vram_gb": 24, "price_per_min": 0.1},
    )
    assert reg_resp.status_code == 200
    provider_id = reg_resp.get_json()["provider_id"]

    sub_resp = client.post(
        "/api/gpu/jobs/submit",
        headers=AUTH,
        json={"job_type": "video_render", "estimated_mins": 2, "max_price_per_min": 0.2},
    )
    assert sub_resp.status_code == 200
    job_id = sub_resp.get_json()["job_id"]

    claim_resp = client.post(
        "/api/gpu/jobs/claim",
        headers=AUTH,
        json={"provider_id": provider_id, "job_id": job_id},
    )
    assert claim_resp.status_code == 200

    start_resp = client.post(
        "/api/gpu/jobs/start",
        headers=AUTH,
        json={"provider_id": provider_id, "job_id": job_id},
    )
    assert start_resp.status_code == 200

    return provider_id, job_id


def test_completed_job_cannot_be_failed_or_reopened(client):
    provider_id, job_id = _setup_provider_and_job(client)

    comp_resp = client.post(
        "/api/gpu/jobs/complete",
        headers=AUTH,
        json={"provider_id": provider_id, "job_id": job_id, "result_url": "https://example.com/out.mp4"},
    )
    assert comp_resp.status_code == 200
    assert comp_resp.get_json()["ok"] is True

    status_resp = client.get(f"/api/gpu/jobs/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.get_json()["status"] == "completed"

    fail_resp = client.post(
        "/api/gpu/jobs/fail",
        headers=AUTH,
        json={"provider_id": provider_id, "job_id": job_id, "error_message": "late failure"},
    )

    assert fail_resp.status_code in (400, 409)
    assert fail_resp.get_json().get("ok") is not True

    status_resp2 = client.get(f"/api/gpu/jobs/{job_id}")
    assert status_resp2.get_json()["status"] == "completed"


def test_active_running_job_can_be_failed_and_released(client):
    provider_id, job_id = _setup_provider_and_job(client)

    fail_resp = client.post(
        "/api/gpu/jobs/fail",
        headers=AUTH,
        json={"provider_id": provider_id, "job_id": job_id, "error_message": "OOM error"},
    )
    assert fail_resp.status_code == 200
    assert fail_resp.get_json()["ok"] is True

    status_resp = client.get(f"/api/gpu/jobs/{job_id}")
    assert status_resp.get_json()["status"] == "pending"


def test_active_claimed_job_can_be_failed_and_released(client):
    reg_resp = client.post(
        "/api/gpu/providers/register",
        headers=AUTH,
        json={"gpu_model": "RTX 4090", "gpu_vram_gb": 24, "price_per_min": 0.1},
    )
    provider_id = reg_resp.get_json()["provider_id"]

    sub_resp = client.post(
        "/api/gpu/jobs/submit",
        headers=AUTH,
        json={"job_type": "video_render", "estimated_mins": 2, "max_price_per_min": 0.2},
    )
    job_id = sub_resp.get_json()["job_id"]

    claim_resp = client.post(
        "/api/gpu/jobs/claim",
        headers=AUTH,
        json={"provider_id": provider_id, "job_id": job_id},
    )
    assert claim_resp.status_code == 200

    fail_resp = client.post(
        "/api/gpu/jobs/fail",
        headers=AUTH,
        json={"provider_id": provider_id, "job_id": job_id, "error_message": "Driver crash"},
    )
    assert fail_resp.status_code == 200
    assert fail_resp.get_json()["ok"] is True

    status_resp = client.get(f"/api/gpu/jobs/{job_id}")
    assert status_resp.get_json()["status"] == "pending"

