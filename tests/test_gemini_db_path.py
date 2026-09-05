# SPDX-License-Identifier: MIT
import importlib
import os
import sqlite3
from pathlib import Path


def test_gemini_uses_bottube_db_path_for_app_and_worker(tmp_path, monkeypatch):
    """Verify gemini_blueprint uses BOTTUBE_DB_PATH for both app and worker.

    The gemini jobs table is read by the Flask app and written by a
    background worker. Both code paths must resolve to the same DB
    file when BOTTUBE_DB_PATH is set in the environment, otherwise a
    job created by the worker would be invisible to the app (and vice
    versa). This test pins init_gemini_tables, get_db, and _update_job
    to the same custom path and asserts the row written by _update_job
    is visible to a direct sqlite3 connection.
    """
    db_dir = tmp_path / "custom-db-dir"
    db_dir.mkdir()
    db_path = db_dir / "bottube.db"

    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    monkeypatch.delenv("BOTTUBE_DB", raising=False)

    import gemini_blueprint
    importlib.reload(gemini_blueprint)

    gemini_blueprint.init_gemini_tables()
    assert db_path.exists(), "init_gemini_tables() should create the configured DB file"

    from flask import Flask

    app = Flask(__name__)
    app.config["TESTING"] = True

    with app.app_context():
        db = gemini_blueprint.get_db()
        row = db.execute("PRAGMA database_list").fetchone()
        assert Path(row[2]) == db_path

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO gemini_jobs (job_id, agent_id, job_type, model, prompt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("job-1", 1, "video", "veo", "prompt", 0),
    )
    conn.commit()
    conn.close()

    gemini_blueprint._update_job(str(db_path), "job-1", "completed", result_path="/tmp/out.mp4")

    conn = sqlite3.connect(db_path)
    status, result_path = conn.execute(
        "SELECT status, result_path FROM gemini_jobs WHERE job_id = ?",
        ("job-1",),
    ).fetchone()
    conn.close()

    assert status == "completed"
    assert result_path == "/tmp/out.mp4"
