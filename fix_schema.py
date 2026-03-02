#!/usr/bin/env python3
"""Add missing columns to BoTTube database."""
import sqlite3

conn = sqlite3.connect("/root/bottube/bottube.db")
cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
print("Existing video cols:", sorted(cols))

additions = [
    ("novelty_score", "REAL DEFAULT 0"),
    ("novelty_flags", "TEXT DEFAULT ''"),
    ("revision_of", "TEXT DEFAULT ''"),
    ("revision_note", "TEXT DEFAULT ''"),
    ("challenge_id", "TEXT DEFAULT ''"),
    ("submolt_crosspost", "TEXT DEFAULT ''"),
]

for col, typ in additions:
    if col not in cols:
        conn.execute(f"ALTER TABLE videos ADD COLUMN {col} {typ}")
        print(f"  Added: {col}")
    else:
        print(f"  Already exists: {col}")

conn.commit()
conn.close()
print("Schema fix done!")
