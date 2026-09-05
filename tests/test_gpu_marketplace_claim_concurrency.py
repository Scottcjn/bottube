# SPDX-License-Identifier: MIT
"""Concurrency regressions for GPU marketplace job admission."""

import sqlite3
import threading

from gpu_marketplace import _claim_gpu_job_transaction, init_gpu_tables


def _seed_provider(db, provider_id, agent_id):
    db.execute(
        """
        INSERT INTO gpu_providers
            (id, agent_id, gpu_model, price_per_min, status, created_at)
        VALUES (?, ?, 'test-gpu', 0.1, 'online', 1)
        """,
        (provider_id, agent_id),
    )


def _seed_job(db, job_id):
    db.execute(
        """
        INSERT INTO gpu_jobs
            (id, requester_id, job_type, job_params, status, rtc_escrowed, created_at)
        VALUES (?, 99, 'video_render', '{}', 'pending', 1.0, 1)
        """,
        (job_id,),
    )


def _race_claims(db_path, claims):
    gate = threading.Barrier(len(claims))
    results = []
    lock = threading.Lock()

    def claim(provider_id, agent_id, job_id):
        db = sqlite3.connect(db_path, timeout=5)
        gate.wait(timeout=2)
        outcome = _claim_gpu_job_transaction(db, provider_id, agent_id, job_id, 10)
        db.close()
        with lock:
            results.append((provider_id, job_id, outcome))

    workers = [threading.Thread(target=claim, args=entry) for entry in claims]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=7)
    assert all(not worker.is_alive() for worker in workers)
    return results


def test_same_job_has_exactly_one_provider_winner(tmp_path):
    db_path = tmp_path / "gpu-same-job.db"
    init_gpu_tables(str(db_path))
    db = sqlite3.connect(db_path)
    _seed_provider(db, "provider-a", 1)
    _seed_provider(db, "provider-b", 2)
    _seed_job(db, "job-one")
    db.commit()
    db.close()

    results = _race_claims(
        db_path,
        [("provider-a", 1, "job-one"), ("provider-b", 2, "job-one")],
    )

    assert sorted(result[2] for result in results) == ["claimed", "job_unavailable"]
    db = sqlite3.connect(db_path)
    provider_id = db.execute("SELECT provider_id FROM gpu_jobs WHERE id = 'job-one'").fetchone()[0]
    statuses = dict(db.execute("SELECT id, status FROM gpu_providers"))
    db.close()
    assert statuses[provider_id] == "busy"
    assert sum(status == "busy" for status in statuses.values()) == 1


def test_same_provider_cannot_reserve_two_jobs(tmp_path):
    db_path = tmp_path / "gpu-same-provider.db"
    init_gpu_tables(str(db_path))
    db = sqlite3.connect(db_path)
    _seed_provider(db, "provider-a", 1)
    _seed_job(db, "job-one")
    _seed_job(db, "job-two")
    db.commit()
    db.close()

    results = _race_claims(
        db_path,
        [("provider-a", 1, "job-one"), ("provider-a", 1, "job-two")],
    )

    assert sorted(result[2] for result in results) == ["claimed", "provider_busy"]
    db = sqlite3.connect(db_path)
    states = list(db.execute("SELECT status, provider_id FROM gpu_jobs ORDER BY id"))
    provider_status = db.execute(
        "SELECT status FROM gpu_providers WHERE id = 'provider-a'"
    ).fetchone()[0]
    db.close()
    assert sorted(state[0] for state in states) == ["claimed", "pending"]
    assert sum(state[1] == "provider-a" for state in states) == 1
    assert provider_status == "busy"
