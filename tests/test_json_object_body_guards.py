# SPDX-License-Identifier: MIT
"""Regression test for non-dict JSON body shape across bridge, admin scraper, and x402 endpoints."""

import json
import sqlite3
import pytest
from flask import Flask, g

import wrtc_bridge
from wrtc_bridge import wrtc_bridge_bp
import scraper_detective
from scraper_detective import scraper_bp
import bottube_x402


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_json_shape.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            sol_address TEXT,
            rtc_balance REAL DEFAULT 100.0,
            coinbase_address TEXT,
            coinbase_wallet_created INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO agents (agent_name, api_key, sol_address, rtc_balance)
        VALUES ('testagent', 'sk_test_12345', '11111111111111111111111111111111', 100.0)
        """
    )
    conn.commit()
    conn.close()

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["DATABASE"] = db_path

    monkeypatch.setattr(wrtc_bridge, "ADMIN_KEY", "test_admin_key")
    import bottube_server
    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test_admin_key")

    def _test_get_db():
        if "test_db" not in g:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            g.test_db = conn
        return g.test_db

    monkeypatch.setattr(wrtc_bridge, "_get_db", _test_get_db)

    app.register_blueprint(wrtc_bridge_bp)
    app.register_blueprint(scraper_bp)
    bottube_x402.init_app(app, db_path)

    @app.teardown_appcontext
    def close_db(exc=None):
        db = g.pop("test_db", None)
        if db is not None:
            db.close()

    return app


@pytest.mark.parametrize(
    "payload",
    [
        [1, 2, 3],
        "just-a-string",
        42,
        3.14,
        True,
    ],
)
def test_wrtc_bridge_deposit_rejects_non_object_json(test_app, payload):
    client = test_app.test_client()
    resp = client.post(
        "/api/bridge/deposit",
        headers={"X-API-Key": "sk_test_12345"},
        json=payload,
    )
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}


@pytest.mark.parametrize(
    "payload",
    [
        [1, 2, 3],
        "just-a-string",
        42,
        3.14,
        True,
    ],
)
def test_wrtc_bridge_withdraw_rejects_non_object_json(test_app, payload):
    client = test_app.test_client()
    resp = client.post(
        "/api/bridge/withdraw",
        headers={"X-API-Key": "sk_test_12345"},
        json=payload,
    )
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}


@pytest.mark.parametrize(
    "payload",
    [
        [1, 2, 3],
        "just-a-string",
        42,
        3.14,
        True,
    ],
)
def test_scraper_admin_block_rejects_non_object_json(test_app, payload):
    client = test_app.test_client()
    resp = client.post(
        "/api/admin/scrapers/block",
        headers={"X-Admin-Key": "test_admin_key"},
        json=payload,
    )
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}


@pytest.mark.parametrize(
    "payload",
    [
        [1, 2, 3],
        "just-a-string",
        42,
        3.14,
        True,
    ],
)
def test_scraper_admin_unblock_rejects_non_object_json(test_app, payload):
    client = test_app.test_client()
    resp = client.post(
        "/api/admin/scrapers/unblock",
        headers={"X-Admin-Key": "test_admin_key"},
        json=payload,
    )
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}


@pytest.mark.parametrize(
    "payload",
    [
        [1, 2, 3],
        "just-a-string",
        42,
        3.14,
        True,
    ],
)
def test_x402_coinbase_wallet_rejects_non_object_json(test_app, payload):
    client = test_app.test_client()
    resp = client.post(
        "/api/agents/me/coinbase-wallet",
        headers={"Authorization": "Bearer sk_test_12345"},
        json=payload,
    )
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}
