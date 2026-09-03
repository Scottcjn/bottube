import pytest
import threading
import time
import os
import bottube_server
from gpu_marketplace import init_gpu_db, get_db
from bottube_server import app as flask_app, init_db

@pytest.fixture
def client(tmp_path):
    # Use a temporary DB so each test run is isolated and matches what get_db() opens
    db_file = str(tmp_path / "test_bottube.db")
    os.environ["BOTTUBE_DB_PATH"] = db_file
    # Monkeypatch the hardcoded DB_PATH so init_db() uses the same temp DB as get_db()
    original_db_path = bottube_server.DB_PATH
    bottube_server.DB_PATH = type(original_db_path)(db_file)
    
    flask_app.config['TESTING'] = True
    with flask_app.app_context():
        init_db()
        init_gpu_db()
        db = get_db()
        
        # Seed agent: id INTEGER, created_at REAL
        db.execute("""
            INSERT OR IGNORE INTO agents (id, agent_name, display_name, api_key, is_banned, created_at)
            VALUES (1, 'test-agent', 'Test Agent', 'test-key', 0, ?)
        """, (float(time.time()),))
        
        # Seed provider: agent_id must match agent.id (INTEGER)
        now = int(time.time())
        db.execute("""
            INSERT OR IGNORE INTO gpu_providers (id, agent_id, gpu_model, status, price_per_min, total_jobs, total_rtc_earned, created_at)
            VALUES ('prov1', 1, 'RTX4090', 'online', 0.1, 0, 0.0, ?)
        """, (now,))
        
        # Seed job: requester_id INTEGER, created_at INTEGER NOT NULL, job_type TEXT NOT NULL
        now = int(time.time())
        db.execute("""
            INSERT OR IGNORE INTO gpu_jobs (id, requester_id, provider_id, job_type, job_params, status, started_at, rtc_escrowed, created_at)
            VALUES ('job1', 1, 'prov1', 'video_render', '{}', 'running', ?, 10.0, ?)
        """, (now - 60, now - 120))
        db.commit()
        
        yield flask_app.test_client()
    
    # Cleanup env
    if "BOTTUBE_DB_PATH" in os.environ:
        del os.environ["BOTTUBE_DB_PATH"]
    bottube_server.DB_PATH = original_db_path

def test_concurrent_complete_only_one_wins(client):
    results = []
    def complete():
        r = client.post('/api/gpu/jobs/complete', json={
            "provider_id": "prov1",
            "job_id": "job1"
        }, headers={"X-API-Key": "test-key"})
        results.append(r.status_code)

    t1 = threading.Thread(target=complete)
    t2 = threading.Thread(target=complete)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert sorted(results) == [200, 409], f"Expected [200, 409] but got {sorted(results)}"

    with flask_app.app_context():
        db = get_db()
        history_count = db.execute("SELECT COUNT(*) FROM gpu_job_history WHERE job_id='job1'").fetchone()[0]
        provider = db.execute("SELECT total_jobs, total_rtc_earned FROM gpu_providers WHERE id='prov1'").fetchone()
        assert history_count == 1, f"Expected 1 history row, got {history_count}"
        assert provider[0] == 1, f"Expected total_jobs=1, got {provider[0]}"
        assert provider[1] > 0 and provider[1] <= 10.0, f"Unexpected rtc_earned: {provider[1]}"

def test_complete_after_completed_rejected(client):
    r1 = client.post('/api/gpu/jobs/complete', json={
        "provider_id": "prov1", "job_id": "job1"
    }, headers={"X-API-Key": "test-key"})
    assert r1.status_code == 200

    r2 = client.post('/api/gpu/jobs/complete', json={
        "provider_id": "prov1", "job_id": "job1"
    }, headers={"X-API-Key": "test-key"})
    assert r2.status_code == 409
