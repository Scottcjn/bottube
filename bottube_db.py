# SPDX-License-Identifier: MIT
from pathlib import Path
import os


def resolve_db_path() -> str:
    """Resolve the BoTTube SQLite path consistently across server and blueprints.

    Precedence:
    1. BOTTUBE_DB_PATH (canonical name used by the main server)
    2. BOTTUBE_DB (legacy alias kept for backward compatibility)
    3. BOTTUBE_BASE_DIR/bottube.db
    4. repo-local bottube.db next to this file
    """
    explicit = os.environ.get("BOTTUBE_DB_PATH") or os.environ.get("BOTTUBE_DB")
    if explicit:
        return explicit
    base_dir = Path(os.environ.get("BOTTUBE_BASE_DIR", str(Path(__file__).resolve().parent)))
    return str(base_dir / "bottube.db")
