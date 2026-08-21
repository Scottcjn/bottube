# SPDX-License-Identifier: MIT
"""Single place that decides which SQLite file the app talks to.

The bridge blueprints used to resolve this themselves with
``os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")`` while
``bottube_server`` created their tables using
``os.environ.get("BOTTUBE_DB_PATH", str(DB_PATH))``. Two names, two
defaults, so unless an operator happened to set *both* variables to the
same value the bridges read a different file than the one their tables
were created in.

Resolution order:

1. ``BOTTUBE_DB_PATH`` — the name ``bottube_server`` uses.
2. ``BOTTUBE_DB`` — the name the bridge blueprints used; kept as an alias
   so existing deployments configured that way keep working.
3. ``<BOTTUBE_BASE_DIR or this directory>/bottube.db`` — the same default
   ``bottube_server`` computes, rather than a hardcoded ``/root`` path.
"""
from __future__ import annotations

import os
from pathlib import Path


def resolve_db_path() -> str:
    """Return the path of the SQLite database every module should share."""
    explicit = os.environ.get("BOTTUBE_DB_PATH", "") or os.environ.get("BOTTUBE_DB", "")
    if explicit:
        return explicit
    base_dir = Path(
        os.environ.get("BOTTUBE_BASE_DIR", str(Path(__file__).resolve().parent))
    )
    return str(base_dir / "bottube.db")
