# SPDX-License-Identifier: Apache-2.0
import sqlite3

import avap_blueprint


def test_init_avap_tables_uses_env_base_dir(monkeypatch, tmp_path):
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
