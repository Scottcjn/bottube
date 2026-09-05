# SPDX-License-Identifier: MIT
"""State-integrity regressions for starting GPU jobs."""

import sqlite3
import threading

from gpu_marketplace import _start_gpu_job_transaction, init_gpu_tables


def _seed_job(db, *, status="claimed", provider_id="provider-a"):
    db.execute(
        """
        INSERT INTO gpu_jobs
            (id, requester_id, provider_id, job_type, job_params, status,
             rtc_escrowed, created_at, claimed_at)
        VALUES ('job-one', 99, ?, 'video_render', '{}', ?, 5.0, 1, 2)
        """,
        (provider_id, status),
    )


def test_released_job_cannot_be_started_from_stale_claim(tmp_path):
    db_path = tmp_path / "gpu-stale-start.db"
    init_gpu_tables(str(db_path))
    db = sqlite3.connect(db_path)
    _seed_job(db, status="pending", provider_id=None)
    db.commit()

    assert _start_gpu_job_transaction(db, "provider-a", "job-one", 10) is False
    job = db.execute(
        "SELECT status, provider_id, started_at FROM gpu_jobs WHERE id = 'job-one'"
    ).fetchone()
    db.close()
    assert job == ("pending", None, None)


def test_concurrent_starts_have_exactly_one_winner(tmp_path):
    db_path = tmp_path / "gpu-start-race.db"
    init_gpu_tables(str(db_path))
    db = sqlite3.connect(db_path)
    _seed_job(db)
    db.commit()
    db.close()

    gate = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def start(now):
        connection = sqlite3.connect(db_path, timeout=5)
        gate.wait(timeout=2)
        result = _start_gpu_job_transaction(connection, "provider-a", "job-one", now)
        connection.close()
        with lock:
            results.append(result)

    workers = [threading.Thread(target=start, args=(now,)) for now in (10, 20)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=7)

    assert all(not worker.is_alive() for worker in workers)
    assert sorted(results) == [False, True]
    db = sqlite3.connect(db_path)
    job = db.execute(
        "SELECT status, provider_id, started_at FROM gpu_jobs WHERE id = 'job-one'"
    ).fetchone()
    db.close()
    assert job[0:2] == ("running", "provider-a")
    assert job[2] in {10, 20}
