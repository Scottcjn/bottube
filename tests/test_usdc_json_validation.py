# SPDX-License-Identifier: MIT

import sqlite3

from flask import Flask

from usdc_blueprint import usdc_bp


def create_app(tmp_path, monkeypatch):
    db_path = tmp_path / "bottube.sqlite3"
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE agents (name TEXT, api_key TEXT)")
    db.execute(
        "INSERT INTO agents (name, api_key) VALUES (?, ?)",
        ("alice", "secret"),
    )
    db.commit()
    db.close()

    monkeypatch.setenv("BOTTUBE_DB", str(db_path))
    app = Flask(__name__)
    app.register_blueprint(usdc_bp)
    return app


def auth_headers():
    return {"X-API-Key": "secret"}


def test_usdc_deposit_rejects_non_object_json(tmp_path, monkeypatch):
    client = create_app(tmp_path, monkeypatch).test_client()

    response = client.post(
        "/api/usdc/deposit",
        json="not-object",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_usdc_deposit_rejects_non_string_tx_hash(tmp_path, monkeypatch):
    client = create_app(tmp_path, monkeypatch).test_client()

    response = client.post(
        "/api/usdc/deposit",
        json={"tx_hash": ["0x123"]},
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "tx_hash must be a string"}


def test_usdc_premium_rejects_non_object_json(tmp_path, monkeypatch):
    client = create_app(tmp_path, monkeypatch).test_client()

    response = client.post(
        "/api/usdc/premium",
        json="not-object",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_usdc_premium_rejects_non_string_tier(tmp_path, monkeypatch):
    client = create_app(tmp_path, monkeypatch).test_client()

    response = client.post(
        "/api/usdc/premium",
        json={"tier": ["basic"]},
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "tier must be a string"}


def test_verify_payment_rejects_non_object_json():
    app = Flask(__name__)
    app.register_blueprint(usdc_bp)
    client = app.test_client()

    response = client.post("/api/usdc/verify-payment", json="not-object")

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_verify_payment_rejects_non_string_tx_hash():
    app = Flask(__name__)
    app.register_blueprint(usdc_bp)
    client = app.test_client()

    response = client.post("/api/usdc/verify-payment", json={"tx_hash": ["0x123"]})

    assert response.status_code == 400
    assert response.get_json() == {"error": "tx_hash must be a string"}
