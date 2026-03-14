#!/usr/bin/env python3
"""Add missing columns to BoTTube database."""
from __future__ import annotations
import sqlite3
from typing import Set, Tuple, List


def get_existing_columns(conn: sqlite3.Connection, table_name: str) -> Set[str]:
    """Get existing column names for a table."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    return cols


def add_column_if_missing(conn: sqlite3.Connection, table_name: str, col: str, typ: str) -> None:
    """Add a column to the table if it doesn't exist."""
    cols = get_existing_columns(conn, table_name)
    if col not in cols:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {typ}")
        print(f"  Added: {col}")
    else:
        print(f"  Already exists: {col}")


def fix_schema(db_path: str = "/root/bottube/bottube.db") -> None:
    """Add missing columns to the videos table."""
    conn: sqlite3.Connection = sqlite3.connect(db_path)
    try:
        cols: Set[str] = get_existing_columns(conn, "videos")
        print("Existing video cols:", sorted(cols))

        additions: List[Tuple[str, str]] = [
            ("novelty_score", "REAL DEFAULT 0"),
            ("novelty_flags", "TEXT DEFAULT ''"),
            ("revision_of", "TEXT DEFAULT ''"),
            ("revision_note", "TEXT DEFAULT ''"),
            ("challenge_id", "TEXT DEFAULT ''"),
            ("submolt_crosspost", "TEXT DEFAULT ''"),
        ]

        for col, typ in additions:
            add_column_if_missing(conn, "videos", col, typ)

        conn.commit()
        print("Schema fix done!")
    finally:
        conn.close()


if __name__ == "__main__":
    fix_schema()
