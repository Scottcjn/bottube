# SPDX-License-Identifier: Apache-2.0
import sqlite3

import avap_blueprint


def test_init_avap_tables_uses_env_base_dir(monkeypatch, tmp_path):
    """Verify init_avap_tables creates tables under the configured DB_PATH.

    The avap blueprint reads DB_PATH at import time. When the deployment
    sets BOTTUBE_BASE_DIR (or similar) to a custom location, init_avap_tables
    must honor that path so the schema lands in the same SQLite file the
    rest of the app reads from. This test monkeypatches DB_PATH to a
    tmp_path location and asserts the expected tables exist there.
    """
    db_dir = tmp_path / "custom-base"
    db_dir.mkdir()
    db_path = db_dir / "bottube.db"

    monkeypatch.setattr(avap_blueprint, "DB_PATH", db_path)
    avap_blueprint.init_avap_tables()

    conn = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()

    assert "avap_envelopes" in tables
    assert "avap_anchors" in tables
