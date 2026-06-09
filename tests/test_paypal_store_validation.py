# SPDX-License-Identifier: MIT
"""Validation tests for PayPal store request parsing."""

import sqlite3
from importlib import metadata

import pytest
import werkzeug
from flask import Flask, g

import paypal_packages

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "store.db"
    with sqlite3.connect(db_path) as db:
        db.executescript(paypal_packages.STORE_SCHEMA)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(paypal_packages.store_bp)

    def _test_get_db():
        if "test_db" in g:
            return g.test_db
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        g.test_db = db
        return db

    monkeypatch.setattr(paypal_packages, "get_db", _test_get_db)

    test_client = app.test_client()
    test_client.db_path = db_path
    return test_client


def _order_count(client):
    with sqlite3.connect(client.db_path) as db:
        return db.execute("SELECT COUNT(*) FROM store_orders").fetchone()[0]


def test_store_checkout_rejects_non_object_json_before_paypal_call(client, monkeypatch):
    monkeypatch.setattr(
        paypal_packages,
        "create_paypal_order",
        lambda *_args, **_kwargs: pytest.fail("PayPal order should not be created"),
    )

    resp = client.post("/api/store/checkout", json=["not", "an", "object"])

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"
    assert _order_count(client) == 0


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"package_id": ["creator"], "email": "buyer@example.com"}, "package_id must be a string"),
        ({"package_id": "creator", "agent_id": ["123"]}, "agent_id must be an integer"),
        ({"package_id": "creator", "agent_id": True}, "agent_id must be an integer"),
        ({"package_id": "creator", "agent_id": 0}, "agent_id must be a positive integer"),
        ({"package_id": "creator", "agent_id": -1}, "agent_id must be a positive integer"),
        ({"package_id": "creator", "email": ["buyer@example.com"]}, "email must be a string"),
    ],
)
def test_store_checkout_rejects_malformed_fields_before_paypal_call(
    client,
    monkeypatch,
    payload,
    error,
):
    monkeypatch.setattr(
        paypal_packages,
        "create_paypal_order",
        lambda *_args, **_kwargs: pytest.fail("PayPal order should not be created"),
    )

    resp = client.post("/api/store/checkout", json=payload)

    assert resp.status_code == 400
    assert resp.get_json()["error"] == error
    assert _order_count(client) == 0


def test_paypal_webhook_rejects_non_object_json_before_signature_check(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        paypal_packages,
        "verify_paypal_webhook_signature",
        lambda *_args, **_kwargs: pytest.fail("signature should not be verified"),
    )

    resp = client.post("/api/store/webhook/paypal", json=["not", "an", "object"])

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"
