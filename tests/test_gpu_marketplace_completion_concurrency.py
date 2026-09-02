# SPDX-License-Identifier: MIT
"""Exactly-once settlement regressions for the GPU marketplace."""

import sqlite3
import threading

from gpu_marketplace import _complete_gpu_job_transaction, init_gpu_tables


def test_concurrent_completions_credit_provider_once(tmp_path):
    db_path = tmp_path / "gpu-completion.db"
    init_gpu_tables(str(db_path))
    db = sqlite3.connect(db_path)
    db.execute(
        """
        INSERT INTO gpu_providers
            (id, agent_id, gpu_model, price_per_min, status, total_jobs, total_rtc_earned, created_at)
        VALUES ('provider-a', 1, 'test-gpu', 0.1, 'busy', 0, 0, 1)
        """
    )
    db.execute(
        """
        INSERT INTO gpu_jobs
            (id, requester_id, provider_id, job_type, job_params, status,
             rtc_escrowed, created_at, claimed_at, started_at)
        VALUES ('job-one', 99, 'provider-a', 'video_render', '{}', 'running',
                5.0, 1, 2, 3)
        """
    )
    db.commit()
    db.close()

    gate = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def complete():
        connection = sqlite3.connect(db_path, timeout=5)
        gate.wait(timeout=2)
        result = _complete_gpu_job_transaction(
            connection,
            job_id="job-one",
            provider_id="provider-a",
            now=63,
            duration_mins=1.0,
            payment=0.1,
            result_url="https://example.com/result.mp4",
        )
        connection.close()
        with lock:
            results.append(result)

    workers = [threading.Thread(target=complete) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=7)

    assert all(not worker.is_alive() for worker in workers)
    assert sorted(results) == [False, True]

    db = sqlite3.connect(db_path)
    job = db.execute(
        "SELECT status, rtc_paid, result_url FROM gpu_jobs WHERE id = 'job-one'"
    ).fetchone()
    provider = db.execute(
        "SELECT status, total_jobs, total_rtc_earned FROM gpu_providers WHERE id = 'provider-a'"
    ).fetchone()
    history = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(rtc_amount), 0) FROM gpu_job_history WHERE job_id = 'job-one'"
    ).fetchone()
    db.close()

    assert job == ("completed", 0.1, "https://example.com/result.mp4")
    assert provider == ("online", 1, 0.1)
    assert history == (1, 0.1)
