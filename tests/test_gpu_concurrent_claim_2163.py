"""Regression tests for #2163: concurrent GPU job claims.

Verifies that:
1. Two providers racing to claim the same job: exactly one wins, other gets 409.
2. A busy provider cannot claim a second job (gets 409).
3. Winning claim atomically transitions job to 'claimed' and provider to 'busy'.
"""
import os
import tempfile
import threading
import time

import pytest

# Must monkeypatch DB_PATH before importing app modules
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["BOTTUBE_DB_PATH"] = _test_db.name

import bottube_server
bottube_server.DB_PATH = _test_db.name

from gpu_marketplace import init_gpu_db


@pytest.fixture(autouse=True)
def fresh_db():
    """Reset DB for each test."""
    bottube_server.init_db()
    init_gpu_db(_test_db.name)
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        # Seed an agent (id is INTEGER PRIMARY KEY, use numeric)
        now_f = float(time.time())
        db.execute("INSERT OR REPLACE INTO agents (id, agent_name, api_key, created_at) VALUES (?, ?, ?, ?)",
                   (1, "Test Agent", "test-key", now_f))
        # Seed two providers owned by same agent, both idle
        now = int(time.time())
        for pid in ("gpu_prov_a", "gpu_prov_b"):
            db.execute("""
                INSERT OR REPLACE INTO gpu_providers (id, agent_id, gpu_model, gpu_vram_gb, price_per_min, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (pid, 1, "RTX4090", 24.0, 1.0, "idle", now))
        # Seed one pending job
        db.execute("""
            INSERT OR REPLACE INTO gpu_jobs (id, requester_id, job_type, job_params, rtc_escrowed, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("job_001", 1, "inference", '{"prompt":"hi"}', 100, "pending", now))
        db.commit()
    yield


@pytest.fixture
def client():
    bottube_server.app.config["TESTING"] = True
    with bottube_server.app.test_client() as c:
        yield c


def _claim(client, provider_id, job_id):
    return client.post("/api/gpu/jobs/claim",
                       json={"provider_id": provider_id, "job_id": job_id},
                       headers={"X-API-Key": "test-key"})


def test_same_job_concurrent_claim_exactly_one_wins(client):
    """Two threads race to claim the same job; exactly one succeeds."""
    import flask
    results = {}
    app = bottube_server.app

    def try_claim(label, prov):
        with app.test_client() as c:
            r = _claim(c, prov, "job_001")
        results[label] = (r.status_code, r.get_json())

    t1 = threading.Thread(target=try_claim, args=("a", "gpu_prov_a"))
    t2 = threading.Thread(target=try_claim, args=("b", "gpu_prov_b"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    codes = sorted([results["a"][0], results["b"][0]])
    assert codes == [200, 409], f"Expected one 200 and one 409, got {codes}"

    winner = "a" if results["a"][0] == 200 else "b"
    win_prov = "gpu_prov_a" if winner == "a" else "gpu_prov_b"

    assert results[winner][1]["ok"] is True
    assert results[winner][1]["job_id"] == "job_001"

    # Verify DB state: job claimed by winner, winner busy, loser still idle
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        jrow = db.execute("SELECT status, provider_id FROM gpu_jobs WHERE id = ?", ("job_001",)).fetchone()
        assert jrow[0] == "claimed"
        assert jrow[1] == win_prov

        prow_win = db.execute("SELECT status FROM gpu_providers WHERE id = ?", (win_prov,)).fetchone()
        assert prow_win[0] == "busy"

        lose_prov = "gpu_prov_b" if win_prov == "gpu_prov_a" else "gpu_prov_a"
        prow_lose = db.execute("SELECT status FROM gpu_providers WHERE id = ?", (lose_prov,)).fetchone()
        assert prow_lose[0] == "idle"


def test_busy_provider_cannot_claim_second_job(client):
    """A provider that already has a claimed job cannot claim another."""
    # First claim succeeds
    r1 = _claim(client, "gpu_prov_a", "job_001")
    assert r1.status_code == 200

    # Seed a second pending job
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        now = int(time.time())
        db.execute("""
            INSERT INTO gpu_jobs (id, requester_id, job_type, job_params, rtc_escrowed, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("job_002", 1, "inference", '{"prompt":"bye"}', 50, "pending", now))
        db.commit()

    # Same provider tries to claim second job
    r2 = _claim(client, "gpu_prov_a", "job_002")
    assert r2.status_code in (400, 409), f"Expected 400 or 409 for busy provider, got {r2.status_code}"
    data = r2.get_json()
    assert "busy" in data.get("error", "").lower()

    # job_002 must remain pending
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        j2 = db.execute("SELECT status FROM gpu_jobs WHERE id = ?", ("job_002",)).fetchone()
        assert j2[0] == "pending"
