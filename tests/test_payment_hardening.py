import json
import os
import sqlite3
import sys
from importlib import metadata
from pathlib import Path

import pytest
import werkzeug


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_payments_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_payments_bootstrap.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server
import x402_payment

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_payments_test.db"
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    monkeypatch.setenv("BOTTUBE_DB", str(db_path))
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(paypal_packages, "PAYPAL_WEBHOOK_ID", "test-webhook-id", raising=False)
    x402_payment._payment_cache.clear()
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    paypal_packages.init_store_db(str(db_path))
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str, *, rtc_balance: float = 0.0) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, rtc_balance, bio, avatar_url, created_at, last_active)
            VALUES (?, ?, ?, ?, '', '', ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, rtc_balance, 1.0, 1.0),
        )
        db.commit()
        return int(cur.lastrowid)


def test_x402_requires_structured_receipt_and_blocks_cross_endpoint_replay(client, monkeypatch):
    tx_hash = "0x" + ("ab" * 32)

    def _fake_verify(tx_hash_arg, network, recipient):
        assert tx_hash_arg == tx_hash
        assert network == "base"
        assert recipient == x402_payment.USDC_RECEIVING_ADDRESS.lower()
        return (
            {
                "tx_hash": tx_hash_arg,
                "network": network,
                "recipient": recipient,
                "amount_raw": 100,
                "amount_usdc": 0.0001,
                "block_number": 123,
            },
            None,
        )

    monkeypatch.setattr(x402_payment, "_verify_evm_usdc_transfer", _fake_verify)

    no_payment = client.get("/x402/api/search?q=retro")
    assert no_payment.status_code == 402
    assert no_payment.get_json()["payment"]["networks"] == ["base"]

    raw_payment = client.get(
        "/x402/api/search?q=retro",
        headers={"X-PAYMENT": tx_hash},
    )
    assert raw_payment.status_code == 402
    assert raw_payment.get_json()["reason"] == "invalid_payment_format"

    receipt = json.dumps(
        {
            "tx_hash": tx_hash,
            "network": "base",
            "recipient": x402_payment.USDC_RECEIVING_ADDRESS,
            "amount": "0.000100",
        }
    )
    paid = client.get("/x402/api/search?q=retro", headers={"X-PAYMENT": receipt})
    assert paid.status_code == 200
    assert paid.headers["X-Payment-Verified"] == "true"
    assert paid.headers["X-Payment-Network"] == "base"

    replay = client.get("/x402/api/videos", headers={"X-PAYMENT": receipt})
    assert replay.status_code == 402
    assert replay.get_json()["reason"] == "payment_already_consumed"


@pytest.mark.parametrize(
    ("query", "error"),
    [
        ("page=not-a-number", "page must be a positive integer"),
        ("page=0", "page must be a positive integer"),
        ("page=1.5", "page must be a positive integer"),
        ("per_page=not-a-number", "per_page must be a positive integer"),
        ("per_page=0", "per_page must be a positive integer"),
        ("per_page=true", "per_page must be a positive integer"),
    ],
)
def test_x402_video_list_rejects_invalid_pagination(client, monkeypatch, query, error):
    tx_hash = "0x" + ("cd" * 32)

    def _fake_verify(tx_hash_arg, network, recipient):
        return (
            {
                "tx_hash": tx_hash_arg,
                "network": network,
                "recipient": recipient,
                "amount_raw": 100,
                "amount_usdc": 0.0001,
                "block_number": 123,
            },
            None,
        )

    monkeypatch.setattr(x402_payment, "_verify_evm_usdc_transfer", _fake_verify)
    receipt = json.dumps(
        {
            "tx_hash": tx_hash,
            "network": "base",
            "recipient": x402_payment.USDC_RECEIVING_ADDRESS,
            "amount": "0.000100",
        }
    )

    resp = client.get(f"/x402/api/videos?{query}", headers={"X-PAYMENT": receipt})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": error}


def test_store_capture_credits_agent_balance_and_earnings(client, monkeypatch):
    agent_id = _insert_agent("merchant", "bottube_sk_merchant")

    with sqlite3.connect(bottube_server.DB_PATH) as db:
        db.execute(
            """
            INSERT INTO store_orders
                (id, agent_id, email, package_id, amount_usd, rtc_amount,
                 paypal_order_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            ("ord_capture", agent_id, "merchant@example.com", "creator", 15.0, 1000.0, "PAYPAL_ORDER_1", 1),
        )
        db.commit()

    monkeypatch.setattr(
        paypal_packages,
        "capture_paypal_order",
        lambda order_id: {
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": "CAPTURE_1",
                                "amount": {"value": "15.00", "currency_code": "USD"},
                            }
                        ]
                    }
                }
            ],
        },
    )

    resp = client.get("/api/store/capture?token=PAYPAL_ORDER_1")
    assert resp.status_code == 302
    assert "success=1" in resp.headers["Location"]

    with sqlite3.connect(bottube_server.DB_PATH) as db:
        order = db.execute(
            "SELECT status, paypal_capture_id, refund_amount_usd FROM store_orders WHERE id = ?",
            ("ord_capture",),
        ).fetchone()
        agent = db.execute(
            "SELECT rtc_balance FROM agents WHERE id = ?",
            (agent_id,),
        ).fetchone()
        earning = db.execute(
            "SELECT amount, reason FROM earnings WHERE agent_id = ? ORDER BY id DESC LIMIT 1",
            (agent_id,),
        ).fetchone()
        tx = db.execute(
            """
            SELECT transaction_type, external_id, rtc_credited
            FROM store_transactions
            WHERE order_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            ("ord_capture",),
        ).fetchone()

    assert order == ("completed", "CAPTURE_1", 0.0)
    assert agent[0] == pytest.approx(1000.0)
    assert earning == (1000.0, "store_purchase:creator")
    assert tx == ("purchase", "CAPTURE_1", 1000.0)


def test_paypal_webhook_requires_signature_verification(client, monkeypatch):
    monkeypatch.setattr(
        paypal_packages,
        "verify_paypal_webhook_signature",
        lambda headers, event: (False, "invalid_signature"),
    )

    resp = client.post("/api/store/webhook/paypal", json={"event_type": "PING"})
    assert resp.status_code == 401
    assert resp.get_json()["reason"] == "invalid_signature"


def test_paypal_refund_webhook_reverses_rtc_balance_once(client, monkeypatch):
    agent_id = _insert_agent("refundee", "bottube_sk_refundee", rtc_balance=1000.0)

    with sqlite3.connect(bottube_server.DB_PATH) as db:
        db.execute(
            """
            INSERT INTO store_orders
                (id, agent_id, email, package_id, amount_usd, rtc_amount,
                 paypal_order_id, status, created_at, completed_at, paypal_capture_id,
                 refund_amount_usd, refunded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, 0, 0)
            """,
            (
                "ord_refund",
                agent_id,
                "refundee@example.com",
                "creator",
                15.0,
                1000.0,
                "PAYPAL_ORDER_2",
                1,
                2,
                "CAPTURE_2",
            ),
        )
        db.execute(
            """
            INSERT INTO store_transactions
                (order_id, agent_id, package_id, amount_usd, rtc_credited,
                 transaction_type, external_id, note, created_at)
            VALUES (?, ?, ?, ?, ?, 'purchase', ?, 'paypal_capture', ?)
            """,
            ("ord_refund", agent_id, "creator", 15.0, 1000.0, "CAPTURE_2", 2),
        )
        db.commit()

    monkeypatch.setattr(
        paypal_packages,
        "verify_paypal_webhook_signature",
        lambda headers, event: (True, "verified"),
    )

    event = {
        "event_type": "PAYMENT.CAPTURE.REFUNDED",
        "resource": {
            "id": "REFUND_1",
            "sale_id": "CAPTURE_2",
            "amount": {"value": "15.00", "currency_code": "USD"},
            "status": "COMPLETED",
        },
    }
    resp = client.post("/api/store/webhook/paypal", json=event)
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    second = client.post("/api/store/webhook/paypal", json=event)
    assert second.status_code == 200

    with sqlite3.connect(bottube_server.DB_PATH) as db:
        order = db.execute(
            """
            SELECT status, refund_amount_usd, refunded_at
            FROM store_orders
            WHERE id = ?
            """,
            ("ord_refund",),
        ).fetchone()
        agent = db.execute(
            "SELECT rtc_balance FROM agents WHERE id = ?",
            (agent_id,),
        ).fetchone()
        earnings = db.execute(
            """
            SELECT amount, reason
            FROM earnings
            WHERE agent_id = ?
            ORDER BY id DESC
            """,
            (agent_id,),
        ).fetchall()
        refund_rows = db.execute(
            """
            SELECT transaction_type, external_id, rtc_credited
            FROM store_transactions
            WHERE order_id = ? AND transaction_type = 'refund'
            """,
            ("ord_refund",),
        ).fetchall()

    assert order[0] == "refunded"
    assert order[1] == 15.0
    assert order[2] > 0
    assert agent[0] == pytest.approx(0.0)
    assert earnings[0] == (-1000.0, "store_refund:creator")
    assert refund_rows == [("refund", "REFUND_1", -1000.0)]
