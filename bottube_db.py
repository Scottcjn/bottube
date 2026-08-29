"""Canonical resolver for the Bottube SQLite database path.

Resolves the mismatch between BOTTUBE_DB_PATH (used by bottube_server.py
for table creation) and BOTTUBE_DB (used historically by blueprints).

Priority:
1. BOTTUBE_DB_PATH  (canonical, matches server init)
2. BOTTUBE_DB       (legacy alias — keeps existing deployments working)
3. BOTTUBE_BASE_DIR / "bottube.db"
4. Directory of this file / "bottube.db"
"""
from __future__ import annotations

import os
from pathlib import Path


def resolve_db_path() -> str:
    """Return the canonical SQLite database path as a string."""
    path = os.environ.get("BOTTUBE_DB_PATH")
    if path:
        return path

    legacy = os.environ.get("BOTTUBE_DB")
    if legacy:
        return legacy

    base_env = os.environ.get("BOTTUBE_BASE_DIR")
    if base_env:
        return str(Path(base_env) / "bottube.db")

    return str(Path(__file__).resolve().parent / "bottube.db")
