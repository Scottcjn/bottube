"""Regression coverage for Pi payment callback request validation."""

import pytest
from flask import Flask

import pi_payments


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(pi_payments, "PI_API_KEY", "configured-for-validation-test")
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test", PROPAGATE_EXCEPTIONS=False)
    app.register_blueprint(pi_payments.pi_pay_bp)
    return app.test_client()


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/pi/approve", ["not", "an", "object"]),
        ("/pi/approve", {"payment_id": ["payment"]}),
        ("/pi/complete", ["not", "an", "object"]),
        ("/pi/complete", {"payment_id": ["payment"], "txid": "tx"}),
        ("/pi/complete", {"payment_id": "payment", "txid": ["tx"]}),
    ],
)
def test_payment_callbacks_reject_malformed_types_without_500(client, path, payload):
    response = client.post(path, json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"]


def test_approve_preserves_missing_payment_id_contract(client):
    response = client.post("/pi/approve", json={})

    assert response.status_code == 400
    assert response.get_json() == {"error": "payment_id required"}
