"""
generation/db_init.py - Database initialization for generation router
======================================================================
Creates tables and runs migrations.  Safe to call multiple times.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

log = logging.getLogger("generation.db_init")

_MIGRATION_SQL = Path(__file__).parent / "migration.sql"


def init_generation_tables(db_path: str = None):
    """Create generation tables in the BoTTube database.

    Reads migration.sql for CREATE TABLE statements,
    then runs ALTER TABLE for the videos extension columns.
    """
    if db_path is None:
        db_path = os.environ.get(
            "BOTTUBE_DB_PATH",
            str(Path(__file__).resolve().parent.parent / "bottube.db"),
        )

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    # Run the CREATE TABLE statements from migration.sql
    if _MIGRATION_SQL.exists():
        sql = _MIGRATION_SQL.read_text()
        conn.executescript(sql)
        log.info("Generation tables created/verified from migration.sql")

    # Add source columns to videos table (safe -- ignores if exists)
    for col_def in [
        "source_job_id TEXT DEFAULT ''",
        "source_provider TEXT DEFAULT ''",
        "source_model TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(f"ALTER TABLE videos ADD COLUMN {col_def}")
            log.info("Added column to videos: %s", col_def.split()[0])
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.commit()
    conn.close()
    log.info("Generation DB init complete: %s", db_path)
