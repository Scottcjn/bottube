# SPDX-License-Identifier: MIT
import sqlite3

from flask import Flask

import base_wrtc_bridge_blueprint
import bottube_db
import ergo_bridge_blueprint
import usdc_blueprint
import wrtc_bridge_blueprint


def test_resolve_db_path_prefers_bottube_db_path(monkeypatch, tmp_path):
    """Verify resolve_db_path prefers BOTTUBE_DB_PATH over the legacy alias.

    The canonical env var for the DB location is BOTTUBE_DB_PATH; the
    legacy alias BOTTUBE_DB is kept for backward compatibility. When
    both are set, BOTTUBE_DB_PATH must win so a deployment that
    migrated to the new name does not silently fall back to a stale
    legacy path.
    """
    canonical = tmp_path / "canonical.db"
    legacy = tmp_path / "legacy.db"
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(canonical))
    monkeypatch.setenv("BOTTUBE_DB", str(legacy))

    assert bottube_db.resolve_db_path() == str(canonical)


def test_resolve_db_path_falls_back_to_legacy_alias(monkeypatch, tmp_path):
    """Verify resolve_db_path falls back to BOTTUBE_DB when BOTTUBE_DB_PATH is unset.

    Backward compatibility: deployments that still set BOTTUBE_DB (the
    legacy alias) without BOTTUBE_DB_PATH must continue to resolve to
    the path they configured. If we dropped the fallback here, an
    operator who only sets BOTTUBE_DB would suddenly get the default
    location and silently lose access to their data.
    """
    legacy = tmp_path / "legacy.db"
    monkeypatch.delenv("BOTTUBE_DB_PATH", raising=False)
    monkeypatch.setenv("BOTTUBE_DB", str(legacy))

    assert bottube_db.resolve_db_path() == str(legacy)


def test_resolve_db_path_defaults_to_bottube_base_dir(monkeypatch, tmp_path):
    """Verify resolve_db_path defaults to BOTTUBE_BASE_DIR/bottube.db.

    When neither BOTTUBE_DB_PATH nor BOTTUBE_DB is set, the resolver
    must honor BOTTUBE_BASE_DIR and place bottube.db inside it. This
    is the standard production layout (instance/bottube.db) and the
    resolver must mirror it for tests that do not configure either
    DB env var.
    """
    monkeypatch.delenv("BOTTUBE_DB_PATH", raising=False)
    monkeypatch.delenv("BOTTUBE_DB", raising=False)
    monkeypatch.setenv("BOTTUBE_BASE_DIR", str(tmp_path / "instance"))

    assert bottube_db.resolve_db_path() == str((tmp_path / "instance" / "bottube.db"))


def test_crypto_bridge_blueprints_share_resolver(monkeypatch, tmp_path):
    """Verify all crypto bridge blueprints resolve to the same DB path.

    Four bridge blueprints (usdc, wrtc, base_wrtc, ergo) each call
    bottube_db.resolve_db_path() to find the SQLite file. They must
    all resolve to the same path when BOTTUBE_DB_PATH is set, otherwise
    deposits in one bridge would not be visible to the others. The test
    creates a table for each bridge, sets BOTTUBE_DB_PATH, and asserts
    every blueprint's get_db() can read at least one table from the
    shared file inside a Flask app context.
    """
    db_path = tmp_path / "shared.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE usdc_deposits (id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE wrtc_deposits (id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE base_wrtc_deposits (id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE ergo_deposits (id INTEGER PRIMARY KEY)")

    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    monkeypatch.delenv("BOTTUBE_DB", raising=False)

    app = Flask(__name__)
    for module in (
        usdc_blueprint,
        wrtc_bridge_blueprint,
        base_wrtc_bridge_blueprint,
        ergo_bridge_blueprint,
    ):
        with app.app_context():
            db = module.get_db()
            table = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 1").fetchone()
            assert table is not None
