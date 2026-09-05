# SPDX-License-Identifier: MIT
"""State-integrity regressions for GPU job release/failure."""

import sqlite3
import threading

from gpu_marketplace import _release_gpu_job_transaction, init_gpu_tables


def _seed(db, *, status, rtc_paid=0.0):
    db.execute(
        """
        INSERT INTO gpu_providers
            (id, agent_id, gpu_model, price_per_min, status, created_at)
        VALUES ('provider-a', 1, 'test-gpu', 0.1, 'busy', 1)
        """
    )
    db.execute(
        """
        INSERT INTO gpu_jobs
            (id, requester_id, provider_id, job_type, job_params, status,
             rtc_escrowed, rtc_paid, created_at, claimed_at, started_at, completed_at)
        VALUES ('job-one', 99, 'provider-a', 'video_render', '{}', ?,
                5.0, ?, 1, 2, 3, 4)
        """,
        (status, rtc_paid),
    )


def test_completed_paid_job_cannot_be_reopened(tmp_path):
    db_path = tmp_path / "gpu-terminal.db"
    init_gpu_tables(str(db_path))
    db = sqlite3.connect(db_path)
    _seed(db, status="completed", rtc_paid=2.5)
    db.commit()

    assert _release_gpu_job_transaction(db, "provider-a", "job-one", "late failure") is False
    job = db.execute(
        "SELECT status, provider_id, rtc_paid, completed_at FROM gpu_jobs WHERE id = 'job-one'"
    ).fetchone()
    provider_status = db.execute(
        "SELECT status FROM gpu_providers WHERE id = 'provider-a'"
    ).fetchone()[0]
    db.close()

    assert job == ("completed", "provider-a", 2.5, 4)
    assert provider_status == "busy"


def test_concurrent_job_releases_have_one_winner(tmp_path):
    db_path = tmp_path / "gpu-release-race.db"
    init_gpu_tables(str(db_path))
    db = sqlite3.connect(db_path)
    _seed(db, status="running")
    db.commit()
    db.close()

    gate = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def release(message):
        connection = sqlite3.connect(db_path, timeout=5)
        gate.wait(timeout=2)
        result = _release_gpu_job_transaction(connection, "provider-a", "job-one", message)
        connection.close()
        with lock:
            results.append(result)

    workers = [
        threading.Thread(target=release, args=(message,))
        for message in ("worker one", "worker two")
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=7)

    assert all(not worker.is_alive() for worker in workers)
    assert sorted(results) == [False, True]
    db = sqlite3.connect(db_path)
    job = db.execute(
        "SELECT status, provider_id, claimed_at, started_at, error_message FROM gpu_jobs WHERE id = 'job-one'"
    ).fetchone()
    provider_status = db.execute(
        "SELECT status FROM gpu_providers WHERE id = 'provider-a'"
    ).fetchone()[0]
    db.close()
    assert job[0:4] == ("pending", None, None, None)
    assert job[4] in {"worker one", "worker two"}
    assert provider_status == "online"
