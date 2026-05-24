# SPDX-License-Identifier: MIT

import sqlite3

from flask import Flask

from agent_discovery import discovery_bp
from bottube_x402 import init_app as init_x402_app


def test_beacon_verify_rejects_non_object_json():
    app = Flask(__name__)
    app.register_blueprint(discovery_bp)
    client = app.test_client()

    response = client.post("/api/beacon/verify", json="not-object")

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def create_x402_app(tmp_path):
    db_path = tmp_path / "bottube.sqlite3"
    db = sqlite3.connect(db_path)
    db.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT,
            display_name TEXT,
            api_key TEXT,
            coinbase_address TEXT,
            coinbase_wallet_created INTEGER DEFAULT 0
        )
        """
    )
    db.execute(
        "INSERT INTO agents (id, agent_name, display_name, api_key) VALUES (?, ?, ?, ?)",
        (1, "alice", "Alice", "secret"),
    )
    db.commit()
    db.close()

    app = Flask(__name__)
    init_x402_app(app, db_path)
    return app


def test_coinbase_wallet_rejects_non_object_json(tmp_path):
    client = create_x402_app(tmp_path).test_client()

    response = client.post(
        "/api/agents/me/coinbase-wallet",
        json="not-object",
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_coinbase_wallet_rejects_non_string_manual_address(tmp_path):
    client = create_x402_app(tmp_path).test_client()

    response = client.post(
        "/api/agents/me/coinbase-wallet",
        json={"coinbase_address": ["0x123"]},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "coinbase_address must be a string"}


def test_coinbase_wallet_rejects_falsy_non_string_manual_address(tmp_path):
    client = create_x402_app(tmp_path).test_client()

    response = client.post(
        "/api/agents/me/coinbase-wallet",
        json={"coinbase_address": 0},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "coinbase_address must be a string"}
