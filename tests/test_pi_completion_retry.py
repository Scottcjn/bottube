"""Pi completion transport failures must leave a retryable payment row."""

import sqlite3

import requests
from flask import Flask

import pi_payments


class _SuccessResponse:
    status_code = 200
    text = "ok"


def test_transport_failure_releases_completion_claim_for_retry(tmp_path, monkeypatch):
    db_path = tmp_path / "pi-payments.db"
    pi_payments.init_pi_payment_tables(str(db_path))
    monkeypatch.setattr(pi_payments, "PI_API_KEY", "test-key")
    monkeypatch.setattr(pi_payments, "_db_path", lambda: str(db_path))
    monkeypatch.setattr(
        pi_payments,
        "_pi_get_payment",
        lambda _payment_id: {
            "metadata": {"product": "test_payment"},
            "amount": 0.1,
            "user_uid": "pi-user-1",
        },
    )

    calls = iter([requests.Timeout("Pi timed out"), _SuccessResponse()])

    def complete_request(*_args, **_kwargs):
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(pi_payments.requests, "post", complete_request)

    app = Flask(__name__)
    app.register_blueprint(pi_payments.pi_pay_bp)
    client = app.test_client()
    payload = {"payment_id": "payment-1", "txid": "tx-1"}

    failed = client.post("/pi/complete", json=payload)
    assert failed.status_code == 502

    with sqlite3.connect(db_path) as db:
        assert db.execute(
            "SELECT status FROM pi_payments WHERE payment_id='payment-1'"
        ).fetchone()[0] == "approved"

    retried = client.post("/pi/complete", json=payload)
    assert retried.status_code == 200
    assert retried.get_json()["status"] == "completed"

    with sqlite3.connect(db_path) as db:
        assert db.execute(
            "SELECT status, granted FROM pi_payments WHERE payment_id='payment-1'"
        ).fetchone() == ("completed", 1)
