import pytest
import time
import os
import bottube_server
from gpu_marketplace import init_gpu_db, get_db
from bottube_server import app as flask_app, init_db

@pytest.fixture
def client(tmp_path):
    db_file = str(tmp_path / "test_bottube.db")
    os.environ["BOTTUBE_DB_PATH"] = db_file
    original_db_path = bottube_server.DB_PATH
    bottube_server.DB_PATH = type(original_db_path)(db_file)

    flask_app.config['TESTING'] = True
    with flask_app.app_context():
        init_db()
        init_gpu_db()
        db = get_db()

        now = int(time.time())
        db.execute("""
            INSERT OR IGNORE INTO agents (id, agent_name, display_name, api_key, is_banned, created_at)
            VALUES (1, 'test-agent', 'Test Agent', 'test-key', 0, ?)
        """, (float(now),))

        db.execute("""
            INSERT OR IGNORE INTO gpu_providers (id, agent_id, gpu_model, status, price_per_min, total_jobs, total_rtc_earned, created_at)
            VALUES ('prov1', 1, 'RTX4090', 'online', 0.1, 0, 0.0, ?)
        """, (now,))

        # Seed a claimed job
        db.execute("""
            INSERT OR IGNORE INTO gpu_jobs (id, requester_id, provider_id, job_type, job_params, status, started_at, rtc_escrowed, created_at)
            VALUES ('job1', 1, 'prov1', 'video_render', '{}', 'claimed', NULL, 10.0, ?)
        """, (now - 120,))
        db.commit()

        yield flask_app.test_client()

    if "BOTTUBE_DB_PATH" in os.environ:
        del os.environ["BOTTUBE_DB_PATH"]
    bottube_server.DB_PATH = original_db_path


def test_start_claimed_job_succeeds(client):
    r = client.post('/api/gpu/jobs/start', json={
        "provider_id": "prov1", "job_id": "job1"
    }, headers={"X-API-Key": "test-key"})
    assert r.status_code == 200, f"Expected 200 but got {r.status_code}: {r.get_data(as_text=True)}"


def test_stale_start_after_release_rejected(client):
    """Simulate: job is claimed, then released back to pending (e.g. by failure path),
    then a stale start request arrives. Must return 409, not create ownerless running job."""
    # First release the job back to pending (simulating concurrent failure/release)
    with flask_app.app_context():
        db = get_db()
        db.execute("UPDATE gpu_jobs SET status = 'pending', provider_id = NULL WHERE id = 'job1'")
        db.commit()

    r = client.post('/api/gpu/jobs/start', json={
        "provider_id": "prov1", "job_id": "job1"
    }, headers={"X-API-Key": "test-key"})
    assert r.status_code == 409, f"Expected 409 for stale start but got {r.status_code}: {r.get_data(as_text=True)}"

    # Verify no ownerless running job was created
    with flask_app.app_context():
        db = get_db()
        row = db.execute("SELECT status, provider_id FROM gpu_jobs WHERE id = 'job1'").fetchone()
        assert row[0] == 'pending', f"Job should still be pending, got {row[0]}"
        assert row[1] is None, f"Provider should be NULL, got {row[1]}"


def test_duplicate_start_second_rejected(client):
    """Two start requests for the same claimed job: first wins, second gets 409."""
    r1 = client.post('/api/gpu/jobs/start', json={
        "provider_id": "prov1", "job_id": "job1"
    }, headers={"X-API-Key": "test-key"})
    assert r1.status_code == 200

    r2 = client.post('/api/gpu/jobs/start', json={
        "provider_id": "prov1", "job_id": "job1"
    }, headers={"X-API-Key": "test-key"})
    assert r2.status_code == 409, f"Expected 409 for duplicate start but got {r2.status_code}"
