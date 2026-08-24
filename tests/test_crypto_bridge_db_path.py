# SPDX-License-Identifier: MIT
import sqlite3

from flask import Flask

import base_wrtc_bridge_blueprint
import bottube_db
import ergo_bridge_blueprint
import usdc_blueprint
import wrtc_bridge_blueprint


def test_resolve_db_path_prefers_bottube_db_path(monkeypatch, tmp_path):
    canonical = tmp_path / "canonical.db"
    legacy = tmp_path / "legacy.db"
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(canonical))
    monkeypatch.setenv("BOTTUBE_DB", str(legacy))

    assert bottube_db.resolve_db_path() == str(canonical)


def test_resolve_db_path_falls_back_to_legacy_alias(monkeypatch, tmp_path):
    legacy = tmp_path / "legacy.db"
    monkeypatch.delenv("BOTTUBE_DB_PATH", raising=False)
    monkeypatch.setenv("BOTTUBE_DB", str(legacy))

    assert bottube_db.resolve_db_path() == str(legacy)


def test_resolve_db_path_defaults_to_bottube_base_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("BOTTUBE_DB_PATH", raising=False)
    monkeypatch.delenv("BOTTUBE_DB", raising=False)
    monkeypatch.setenv("BOTTUBE_BASE_DIR", str(tmp_path / "instance"))

    assert bottube_db.resolve_db_path() == str((tmp_path / "instance" / "bottube.db"))


def test_crypto_bridge_blueprints_share_resolver(monkeypatch, tmp_path):
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
