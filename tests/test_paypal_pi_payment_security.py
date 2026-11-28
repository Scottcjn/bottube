# SPDX-License-Identifier: MIT
"""Security regression tests for PayPal package store and Pi payment routes."""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from importlib import metadata

import pytest
import requests
import werkzeug
from flask import Flask, g

import paypal_packages
import pi_payments

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


_LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT UNIQUE NOT NULL,
    rtc_balance REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS earnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    reason TEXT NOT NULL,
    video_id TEXT DEFAULT '',
    created_at REAL NOT NULL
);
"""


def _init_store_ledger_db(db_path) -> int:
    with sqlite3.connect(db_path) as db:
        db.executescript(_LEDGER_SCHEMA)
        db.executescript(paypal_packages.STORE_SCHEMA)
        cur = db.execute(
            "INSERT INTO agents (agent_name, rtc_balance) VALUES (?, ?)",
            ("buyer_agent", 0.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_order(
    db_path,
    *,
    order_id: str,
    agent_id: int,
    paypal_order_id: str,
    status: str = "pending",
    amount_usd: float = 200.0,
    rtc_amount: float = 1333.0,
    capture_id: str = "",
    refund_amount_usd: float = 0.0,
):
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            INSERT INTO store_orders
                (id, agent_id, email, package_id, amount_usd, rtc_amount,
                 paypal_order_id, status, created_at, paypal_capture_id, refund_amount_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                order_id,
                agent_id,
                "buyer@example.com",
                "enterprise",
                amount_usd,
                rtc_amount,
                paypal_order_id,
                status,
                capture_id,
                refund_amount_usd,
            ),
        )
        db.commit()


@pytest.fixture()
def store_client(tmp_path, monkeypatch):
    db_path = tmp_path / "paypal_security.db"
    agent_id = _init_store_ledger_db(db_path)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(paypal_packages.store_bp)

    def _test_get_db():
        if "test_db" not in g:
            conn = sqlite3.connect(str(db_path), timeout=30)
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.row_factory = sqlite3.Row
            g.test_db = conn
        return g.test_db

    @app.teardown_appcontext
    def _close_db(_exc):
        conn = g.pop("test_db", None)
        if conn is not None:
            conn.close()

    monkeypatch.setattr(paypal_packages, "get_db", _test_get_db)
    monkeypatch.setattr(paypal_packages, "PAYPAL_WEBHOOK_ID", "wh_test", raising=False)

    client = app.test_client()
    client.db_path = db_path
    client.agent_id = agent_id
    return client


@pytest.fixture()
def pi_client(tmp_path, monkeypatch):
    db_path = tmp_path / "pi_security.db"
    pi_payments.init_pi_payment_tables(str(db_path))
    monkeypatch.setattr(pi_payments, "PI_API_KEY", "pi-test-secret-key")
    monkeypatch.setattr(pi_payments, "_db_path", lambda: str(db_path))

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(pi_payments.pi_pay_bp)

    client = app.test_client()
    client.db_path = db_path
    return client


def test_paypal_complete_order_concurrent_race_credits_once(tmp_path):
    db_path = tmp_path / "race_complete.db"
    agent_id = _init_store_ledger_db(db_path)
    _insert_order(
        db_path,
        order_id="ord_race_1",
        agent_id=agent_id,
        paypal_order_id="PP_RACE_1",
        status="pending",
    )

    barrier = threading.Barrier(4)

    def _worker(idx: int):
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.row_factory = sqlite3.Row
        try:
            stale_order = conn.execute(
                "SELECT * FROM store_orders WHERE id = ?",
                ("ord_race_1",),
            ).fetchone()
            barrier.wait(timeout=5)
            return paypal_packages._complete_order(
                conn,
                stale_order,
                capture_id=f"CAP_RACE_{idx}",
                capture_amount_usd=Decimal("200.00"),
                require_amount=True,
            )
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_worker, i) for i in range(4)]
        results = [f.result(timeout=10) for f in futures]

    assert len(results) == 4
    assert sum(1 for ok, reason in results if ok and reason == "completed") == 1
    assert sum(1 for ok, reason in results if ok and reason == "already_completed") == 3

    with sqlite3.connect(db_path) as db:
        balance = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (agent_id,)).fetchone()[0]
        earnings_count = db.execute("SELECT COUNT(*) FROM earnings WHERE agent_id = ?", (agent_id,)).fetchone()[0]
        tx_count = db.execute(
            "SELECT COUNT(*) FROM store_transactions WHERE order_id = ? AND transaction_type = 'purchase'",
            ("ord_race_1",),
        ).fetchone()[0]

    assert balance == pytest.approx(1333.0)
    assert earnings_count == 1
    assert tx_count == 1


def test_paypal_complete_order_rejects_post_refund_recredit_and_duplicate_capture_id(store_client, monkeypatch):
    _insert_order(
        store_client.db_path,
        order_id="ord_refunded",
        agent_id=store_client.agent_id,
        paypal_order_id="PP_REFUNDED",
        status="refunded",
        amount_usd=15.0,
        rtc_amount=100.0,
        capture_id="CAP_ORIG",
        refund_amount_usd=15.0,
    )
    _insert_order(
        store_client.db_path,
        order_id="ord_second",
        agent_id=store_client.agent_id,
        paypal_order_id="PP_SECOND",
        status="pending",
        amount_usd=15.0,
        rtc_amount=100.0,
    )
    with sqlite3.connect(store_client.db_path) as db:
        db.execute(
            """
            INSERT INTO store_transactions
                (order_id, agent_id, package_id, amount_usd, rtc_credited,
                 transaction_type, external_id, note, created_at)
            VALUES ('ord_refunded', ?, 'creator', 15.0, 100.0, 'purchase', 'CAP_ORIG', 'paypal_capture', 1)
            """,
            (store_client.agent_id,),
        )
        db.commit()

    monkeypatch.setattr(
        paypal_packages,
        "capture_paypal_order",
        lambda *_a, **_kw: pytest.fail("capture API must not be called for refunded order"),
    )
    resp = store_client.get("/api/store/capture?token=PP_REFUNDED")
    assert resp.status_code == 302
    assert "error=already_refunded" in resp.headers["Location"]

    # Replay an already-consumed capture_id against a second pending order
    with sqlite3.connect(store_client.db_path) as db:
        db.row_factory = sqlite3.Row
        second_order = db.execute("SELECT * FROM store_orders WHERE id = 'ord_second'").fetchone()
        ok, reason = paypal_packages._complete_order(
            db,
            second_order,
            capture_id="CAP_ORIG",
            capture_amount_usd=Decimal("15.00"),
            require_amount=True,
        )
        balance = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (store_client.agent_id,)).fetchone()[0]
        second_status = db.execute("SELECT status FROM store_orders WHERE id = 'ord_second'").fetchone()[0]

    assert (ok, reason) == (False, "duplicate_capture_id")
    assert balance == pytest.approx(0.0)
    assert second_status == "pending"


def test_paypal_capture_rejects_non_usd_or_missing_amount_without_clobbering_completed(store_client, monkeypatch):
    _insert_order(
        store_client.db_path,
        order_id="ord_non_usd",
        agent_id=store_client.agent_id,
        paypal_order_id="PP_NON_USD",
        status="pending",
        amount_usd=15.0,
        rtc_amount=100.0,
    )
    monkeypatch.setattr(
        paypal_packages,
        "capture_paypal_order",
        lambda _oid: {
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": "CAP_MXN",
                                "amount": {"value": "15.00", "currency_code": "MXN"},
                            }
                        ]
                    }
                }
            ],
        },
    )

    resp = store_client.get("/api/store/capture?token=PP_NON_USD")
    assert resp.status_code == 302
    assert "error=capture_amount_mismatch" in resp.headers["Location"]

    with sqlite3.connect(store_client.db_path) as db:
        status = db.execute("SELECT status FROM store_orders WHERE id = 'ord_non_usd'").fetchone()[0]
        balance = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (store_client.agent_id,)).fetchone()[0]
    assert status == "failed"
    assert balance == pytest.approx(0.0)


def test_paypal_refund_rejects_uncompleted_order_and_prevents_concurrent_over_refund(tmp_path):
    db_path = tmp_path / "race_refund.db"
    agent_id = _init_store_ledger_db(db_path)
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE agents SET rtc_balance = 1000.0 WHERE id = ?", (agent_id,))
        db.commit()

    _insert_order(
        db_path,
        order_id="ord_pending_norefund",
        agent_id=agent_id,
        paypal_order_id="PP_PENDING",
        status="pending",
        amount_usd=15.0,
        rtc_amount=1000.0,
    )
    _insert_order(
        db_path,
        order_id="ord_paid_refund",
        agent_id=agent_id,
        paypal_order_id="PP_PAID",
        status="completed",
        amount_usd=15.0,
        rtc_amount=1000.0,
        capture_id="CAP_PAID",
    )

    # 1) Pending order cannot be refunded
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        pending_order = db.execute("SELECT * FROM store_orders WHERE id = 'ord_pending_norefund'").fetchone()
        ok, reason = paypal_packages._refund_order(
            db,
            pending_order,
            refund_id="REF_PENDING",
            refund_amount_usd=Decimal("15.00"),
        )
    assert (ok, reason) == (False, "order_not_refundable")

    # 2) Two concurrent $10 partial refunds on a $15 order must clamp total to $15 and -1000 RTC
    barrier = threading.Barrier(2)

    def _refund_worker(refund_id: str):
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.row_factory = sqlite3.Row
        try:
            stale_order = conn.execute(
                "SELECT * FROM store_orders WHERE id = 'ord_paid_refund'"
            ).fetchone()
            barrier.wait(timeout=5)
            return paypal_packages._refund_order(
                conn,
                stale_order,
                refund_id=refund_id,
                refund_amount_usd=Decimal("10.00"),
            )
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_refund_worker, "REF_PARTIAL_1"),
            pool.submit(_refund_worker, "REF_PARTIAL_2"),
        ]
        results = [f.result(timeout=10) for f in futures]

    assert sorted(r[1] for r in results) == ["partially_refunded", "refunded"]

    with sqlite3.connect(db_path) as db:
        status, refunded_usd = db.execute(
            "SELECT status, refund_amount_usd FROM store_orders WHERE id = 'ord_paid_refund'"
        ).fetchone()
        balance = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (agent_id,)).fetchone()[0]
        total_debited = db.execute(
            """
            SELECT SUM(-rtc_credited)
            FROM store_transactions
            WHERE order_id = 'ord_paid_refund' AND transaction_type = 'refund'
            """
        ).fetchone()[0]

    assert status == "refunded"
    assert refunded_usd == pytest.approx(15.0)
    assert total_debited == pytest.approx(1000.0)
    assert balance == pytest.approx(0.0)


def test_paypal_webhook_rejects_malformed_resource_and_checkout_hides_internal_errors(store_client, monkeypatch):
    monkeypatch.setattr(
        paypal_packages,
        "verify_paypal_webhook_signature",
        lambda _headers, _event: (True, "verified"),
    )
    bad_resource = store_client.post(
        "/api/store/webhook/paypal",
        json={"event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": ["not-a-dict"]},
    )
    assert bad_resource.status_code == 400

    monkeypatch.setattr(
        paypal_packages,
        "create_paypal_order",
        lambda *_a, **_kw: (_ for _ in ()).throw(requests.RequestException("internal-secret-url")),
    )
    checkout_err = store_client.post(
        "/api/store/checkout",
        json={"package_id": "starter", "email": "buyer@example.com"},
    )
    assert checkout_err.status_code == 500
    assert checkout_err.get_json() == {"error": "PayPal API error"}
    assert "internal-secret-url" not in checkout_err.get_data(as_text=True)


@pytest.mark.parametrize(
    ("endpoint", "payload"),
    [
        ("/pi/approve", {"payment_id": "../../me"}),
        ("/pi/approve", {"payment_id": "pay123/cancel#"}),
        ("/pi/approve", {"payment_id": "pay123?foo=bar"}),
        ("/pi/approve", {"payment_id": "pay 123"}),
        ("/pi/complete", {"payment_id": "../../me", "txid": "tx-1"}),
        ("/pi/complete", {"payment_id": "pay-1", "txid": "../bad/tx"}),
    ],
)
def test_pi_routes_block_path_traversal_before_upstream_api_call(pi_client, monkeypatch, endpoint, payload):
    monkeypatch.setattr(
        pi_payments.requests,
        "get",
        lambda *_a, **_kw: pytest.fail("upstream GET must not be invoked for malformed identifiers"),
    )
    monkeypatch.setattr(
        pi_payments.requests,
        "post",
        lambda *_a, **_kw: pytest.fail("upstream POST must not be invoked for malformed identifiers"),
    )

    resp = pi_client.post(endpoint, json=payload)
    assert resp.status_code == 400
    assert "invalid" in resp.get_json()["error"]


def test_pi_approve_cannot_downgrade_completed_payment_for_double_grant_and_hides_upstream_body(
    pi_client,
    monkeypatch,
):
    grants = []
    monkeypatch.setattr(
        pi_payments,
        "_pi_get_payment",
        lambda pid: {
            "identifier": pid,
            "metadata": {"product": "test_payment"},
            "amount": 0.1,
            "user_uid": "pi-user-42",
        },
    )

    class _OkResp:
        status_code = 200
        text = "ok"

    class _ErrResp:
        status_code = 403
        text = "SECRET_UPSTREAM_DIAGNOSTIC_TOKEN"

    monkeypatch.setattr(pi_payments.requests, "post", lambda *_a, **_kw: _OkResp())
    monkeypatch.setattr(
        pi_payments,
        "_grant_entitlement",
        lambda uid, product, pid: (grants.append((uid, product, pid)) or True),
    )

    # Complete payment once
    done = pi_client.post("/pi/complete", json={"payment_id": "pay_once_1", "txid": "tx_once_1"})
    assert done.status_code == 200
    assert len(grants) == 1

    # Re-hitting /pi/approve MUST NOT downgrade status from completed -> approved
    downgrade = pi_client.post("/pi/approve", json={"payment_id": "pay_once_1"})
    assert downgrade.status_code == 409

    # Re-hitting /pi/complete MUST NOT grant a second time
    replay = pi_client.post("/pi/complete", json={"payment_id": "pay_once_1", "txid": "tx_once_2"})
    assert replay.status_code == 200
    assert replay.get_json()["duplicate"] is True
    assert len(grants) == 1

    # Upstream error bodies must not be reflected to unauthenticated callers
    monkeypatch.setattr(pi_payments.requests, "post", lambda *_a, **_kw: _ErrResp())
    err_resp = pi_client.post("/pi/approve", json={"payment_id": "pay_upstream_err"})
    assert err_resp.status_code == 502
    body = err_resp.get_json()
    assert body == {"error": "pi approve failed"}
    assert "SECRET_UPSTREAM_DIAGNOSTIC_TOKEN" not in err_resp.get_data(as_text=True)


@pytest.mark.parametrize(
    "payment_payload",
    [
        {"metadata": {"product": "test_payment"}, "amount": True},
        {"metadata": {"product": "test_payment"}, "amount": "NaN"},
        {"metadata": {"product": "test_payment"}, "amount": "inf"},
        {"metadata": {"product": "test_payment"}, "amount": "not-a-number"},
        {"metadata": ["bad-meta"], "amount": 0.1},
        {
            "identifier": "different-payment-id",
            "metadata": {"product": "test_payment"},
            "amount": 0.1,
        },
        {
            "identifier": "pay_bad",
            "metadata": {"product": "test_payment"},
            "amount": 0.1,
            "status": {"user_cancelled": True},
        },
    ],
)
def test_pi_verify_rejects_malformed_bool_nonfinite_cancelled_and_mismatched_payloads(payment_payload):
    product, reason = pi_payments._verify_against_products(
        payment_payload,
        expected_payment_id="pay_bad",
    )
    assert product is None
    assert isinstance(reason, str) and reason
