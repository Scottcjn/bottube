# SPDX-License-Identifier: MIT
"""Security and state-integrity regression tests for GPU marketplace endpoints."""

from __future__ import annotations

import sqlite3
import time

import pytest
import werkzeug
from flask import Flask

from gpu_marketplace import gpu_bp, init_gpu_tables


@pytest.fixture()
def gpu_env(monkeypatch, tmp_path):
    if not hasattr(werkzeug, "__version__"):
        monkeypatch.setattr(werkzeug, "__version__", "test", raising=False)

    db_path = tmp_path / "bottube_gpu_sec.db"
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
        VALUES
            ('funded_agent', 'Funded Agent', 'bottube_sk_funded', 0),
            ('broke_agent', 'Broke Agent', 'bottube_sk_broke', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO balances (miner_id, amount_i64)
        VALUES
            ('funded_agent', 5000000),
            ('broke_agent', 0)
        """
    )
    conn.commit()
    conn.close()
    init_gpu_tables(str(db_path))

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(gpu_bp)
    return app.test_client(), db_path


FUNDED_AUTH = {"X-API-Key": "bottube_sk_funded"}
BROKE_AUTH = {"X-API-Key": "bottube_sk_broke"}


@pytest.mark.parametrize(
    "bad_price",
    [0, -0.5, "NaN", "Infinity", "-Infinity", "not-a-number", True, {"nested": 1}, [1]],
)
def test_register_provider_rejects_invalid_price_per_min(gpu_env, bad_price):
    client, db_path = gpu_env
    resp = client.post(
        "/api/gpu/providers/register",
        headers=FUNDED_AUTH,
        json={"gpu_model": "RTX 4090", "gpu_vram_gb": 24, "price_per_min": bad_price},
    )
    assert resp.status_code == 400
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM gpu_providers").fetchone()[0]
    conn.close()
    assert count == 0


@pytest.mark.parametrize(
    "bad_vram",
    [-1, -24.5, "NaN", "Infinity", "huge", False, {"gb": 24}],
)
def test_register_provider_rejects_invalid_vram(gpu_env, bad_vram):
    client, db_path = gpu_env
    resp = client.post(
        "/api/gpu/providers/register",
        headers=FUNDED_AUTH,
        json={"gpu_model": "RTX 4090", "gpu_vram_gb": bad_vram},
    )
    assert resp.status_code == 400
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM gpu_providers").fetchone()[0]
    conn.close()
    assert count == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"job_type": "video_render", "estimated_mins": -10, "max_price_per_min": 0.1},
        {"job_type": "video_render", "estimated_mins": 0, "max_price_per_min": 0.1},
        {"job_type": "video_render", "estimated_mins": "NaN", "max_price_per_min": 0.1},
        {"job_type": "video_render", "estimated_mins": "Infinity", "max_price_per_min": 0.1},
        {"job_type": "video_render", "estimated_mins": 5, "max_price_per_min": -1.0},
        {"job_type": "video_render", "estimated_mins": 5, "max_price_per_min": 0},
        {"job_type": "video_render", "estimated_mins": 5, "max_price_per_min": "NaN"},
        {"job_type": "video_render", "estimated_mins": 5, "max_price_per_min": "Infinity"},
        {"job_type": "video_render", "estimated_mins": 1e308, "max_price_per_min": 10.0},
        {"job_type": "video_render", "estimated_mins": 5, "max_price_per_min": 0.1, "params": ["not", "dict"]},
    ],
)
def test_submit_job_blocks_negative_nan_inf_overflow_and_non_dict_params(gpu_env, payload):
    client, db_path = gpu_env
    # Even a zero-balance attacker must get 400 and never queue a job
    resp = client.post("/api/gpu/jobs/submit", headers=BROKE_AUTH, json=payload)
    assert resp.status_code == 400
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM gpu_jobs").fetchone()[0]
    conn.close()
    assert count == 0


def _claim_job_with_two_providers(client):
    p1 = client.post(
        "/api/gpu/providers/register",
        headers=FUNDED_AUTH,
        json={"gpu_model": "RTX 4090", "gpu_vram_gb": 24, "price_per_min": 0.1},
    ).get_json()["provider_id"]
    p2 = client.post(
        "/api/gpu/providers/register",
        headers=FUNDED_AUTH,
        json={"gpu_model": "RTX 3080", "gpu_vram_gb": 10, "price_per_min": 0.05},
    ).get_json()["provider_id"]
    job_id = client.post(
        "/api/gpu/jobs/submit",
        headers=FUNDED_AUTH,
        json={"job_type": "video_render", "estimated_mins": 2, "max_price_per_min": 0.2},
    ).get_json()["job_id"]
    assert client.post(
        "/api/gpu/jobs/claim",
        headers=FUNDED_AUTH,
        json={"provider_id": p1, "job_id": job_id},
    ).status_code == 200
    return p1, p2, job_id


def test_start_and_complete_enforce_claiming_provider_id(gpu_env):
    client, _ = gpu_env
    p1, p2, job_id = _claim_job_with_two_providers(client)

    # Same agent using a different provider_id must be rejected on start
    wrong_start = client.post(
        "/api/gpu/jobs/start",
        headers=FUNDED_AUTH,
        json={"provider_id": p2, "job_id": job_id},
    )
    assert wrong_start.status_code == 403

    # Owning provider starts successfully
    ok_start = client.post(
        "/api/gpu/jobs/start",
        headers=FUNDED_AUTH,
        json={"provider_id": p1, "job_id": job_id},
    )
    assert ok_start.status_code == 200

    # Same agent using a different provider_id must be rejected on complete
    wrong_comp = client.post(
        "/api/gpu/jobs/complete",
        headers=FUNDED_AUTH,
        json={"provider_id": p2, "job_id": job_id, "result_url": "https://example.com/v.mp4"},
    )
    assert wrong_comp.status_code == 403


@pytest.mark.parametrize(
    "bad_url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "//evil.example/payload.mp4",
        "https://example.com/ok\r\nX-Injected: 1",
        "http://",
        "not-a-url",
    ],
)
def test_complete_job_rejects_unsafe_result_url(gpu_env, bad_url):
    client, db_path = gpu_env
    p1, _, job_id = _claim_job_with_two_providers(client)
    assert client.post(
        "/api/gpu/jobs/start",
        headers=FUNDED_AUTH,
        json={"provider_id": p1, "job_id": job_id},
    ).status_code == 200

    resp = client.post(
        "/api/gpu/jobs/complete",
        headers=FUNDED_AUTH,
        json={"provider_id": p1, "job_id": job_id, "result_url": bad_url},
    )
    assert resp.status_code == 400
    conn = sqlite3.connect(db_path)
    status = conn.execute("SELECT status FROM gpu_jobs WHERE id = ?", (job_id,)).fetchone()[0]
    conn.close()
    assert status == "running"


def test_complete_job_allows_safe_relative_url_and_clamps_clock_skew_payment(gpu_env):
    client, db_path = gpu_env
    p1, _, job_id = _claim_job_with_two_providers(client)
    assert client.post(
        "/api/gpu/jobs/start",
        headers=FUNDED_AUTH,
        json={"provider_id": p1, "job_id": job_id},
    ).status_code == 200

    # Simulate backward clock skew (started_at in the future) -> payment must clamp to 0.0, never negative
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE gpu_jobs SET started_at = ? WHERE id = ?", (int(time.time()) + 600, job_id))
    conn.commit()
    conn.close()

    resp = client.post(
        "/api/gpu/jobs/complete",
        headers=FUNDED_AUTH,
        json={"provider_id": p1, "job_id": job_id, "result_url": "/api/videos/abc123/stream"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["duration_mins"] == 0.0
    assert body["rtc_earned"] == 0.0

    conn = sqlite3.connect(db_path)
    rtc_paid, result_url = conn.execute(
        "SELECT rtc_paid, result_url FROM gpu_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    earned = conn.execute("SELECT total_rtc_earned FROM gpu_providers WHERE id = ?", (p1,)).fetchone()[0]
    conn.close()
    assert rtc_paid == 0.0
    assert earned == 0.0
    assert result_url == "/api/videos/abc123/stream"
