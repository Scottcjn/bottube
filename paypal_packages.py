#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
BoTTube PayPal Package Store

Sell video generation packages for fiat → RTC credits.
Legal structure: Buying a SERVICE (video generation), not crypto.

Usage:
    1. User selects package on frontend
    2. POST /api/store/checkout → Returns PayPal approval URL
    3. User pays on PayPal
    4. PayPal redirects to /api/store/capture
    5. RTC credits added to user's account

Environment:
    PAYPAL_CLIENT_ID - PayPal REST API client ID
    PAYPAL_CLIENT_SECRET - PayPal REST API secret
    PAYPAL_MODE - "sandbox" or "live"
"""

from __future__ import annotations

import contextlib
import hmac
import os
import secrets
import sqlite3
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import requests
from flask import Blueprint, g, jsonify, redirect, request

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")  # sandbox or live
PAYPAL_WEBHOOK_ID = os.environ.get("PAYPAL_WEBHOOK_ID", "").strip()

# PayPal API endpoints
PAYPAL_API = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com"
}

# Return URLs after PayPal payment
BASE_URL = os.environ.get("BOTTUBE_BASE_URL", "https://bottube.ai")
RETURN_URL = f"{BASE_URL}/api/store/capture"
CANCEL_URL = f"{BASE_URL}/store?cancelled=1"

# ---------------------------------------------------------------------------
# PACKAGE DEFINITIONS
# ---------------------------------------------------------------------------

PACKAGES = {
    "starter": {
        "name": "Starter Pack",
        "description": "5 AI video generations + 33 RTC credits",
        "price_usd": 5.00,
        "rtc_credits": 33,
        "video_generations": 5,
        "gpu_minutes": 10,
    },
    "creator": {
        "name": "Creator Pack",
        "description": "20 AI video generations + 100 RTC credits",
        "price_usd": 15.00,
        "rtc_credits": 100,
        "video_generations": 20,
        "gpu_minutes": 45,
    },
    "studio": {
        "name": "Studio Pack",
        "description": "100 AI video generations + 333 RTC credits",
        "price_usd": 50.00,
        "rtc_credits": 333,
        "video_generations": 100,
        "gpu_minutes": 200,
    },
    "enterprise": {
        "name": "Enterprise Pack",
        "description": "500 AI video generations + 1333 RTC credits",
        "price_usd": 200.00,
        "rtc_credits": 1333,
        "video_generations": 500,
        "gpu_minutes": 1000,
    },
}

# ---------------------------------------------------------------------------
# BLUEPRINT
# ---------------------------------------------------------------------------

store_bp = Blueprint('store', __name__, url_prefix='/api/store')

# ---------------------------------------------------------------------------
# DATABASE SCHEMA
# ---------------------------------------------------------------------------

STORE_SCHEMA = """
-- Purchase orders
CREATE TABLE IF NOT EXISTS store_orders (
    id TEXT PRIMARY KEY,
    agent_id INTEGER,
    email TEXT,
    package_id TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    rtc_amount REAL NOT NULL,
    paypal_order_id TEXT,
    status TEXT DEFAULT 'pending',  -- pending, approved, completed, cancelled, partially_refunded, refunded, failed
    created_at INTEGER NOT NULL,
    completed_at INTEGER,
    paypal_capture_id TEXT,
    refund_amount_usd REAL DEFAULT 0,
    refunded_at INTEGER DEFAULT 0,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- Purchase history for analytics
CREATE TABLE IF NOT EXISTS store_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    agent_id INTEGER,
    package_id TEXT,
    amount_usd REAL,
    rtc_credited REAL,
    transaction_type TEXT,  -- purchase, refund
    external_id TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES store_orders(id)
);

CREATE INDEX IF NOT EXISTS idx_store_orders_status ON store_orders(status);
CREATE INDEX IF NOT EXISTS idx_store_orders_agent ON store_orders(agent_id);
CREATE INDEX IF NOT EXISTS idx_store_orders_paypal ON store_orders(paypal_order_id);
CREATE INDEX IF NOT EXISTS idx_store_orders_capture ON store_orders(paypal_capture_id);
CREATE INDEX IF NOT EXISTS idx_store_transactions_type_external ON store_transactions(transaction_type, external_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_store_transactions_type_external_unique
    ON store_transactions(transaction_type, external_id)
    WHERE external_id IS NOT NULL AND external_id != '';
"""

def init_store_db(db_path: str = None):
    """Initialize store tables in the database."""
    if db_path is None:
        # Default to BoTTube's database path, but allow local/dev checkouts.
        from pathlib import Path
        db_path = os.environ.get(
            "BOTTUBE_DB_PATH",
            str(Path(__file__).resolve().parent / "bottube.db"),
        )

    conn = sqlite3.connect(db_path)
    conn.executescript(STORE_SCHEMA)
    order_cols = {row[1] for row in conn.execute("PRAGMA table_info(store_orders)").fetchall()}
    if "refund_amount_usd" not in order_cols:
        conn.execute("ALTER TABLE store_orders ADD COLUMN refund_amount_usd REAL DEFAULT 0")
    if "refunded_at" not in order_cols:
        conn.execute("ALTER TABLE store_orders ADD COLUMN refunded_at INTEGER DEFAULT 0")

    tx_cols = {row[1] for row in conn.execute("PRAGMA table_info(store_transactions)").fetchall()}
    if "external_id" not in tx_cols:
        conn.execute("ALTER TABLE store_transactions ADD COLUMN external_id TEXT DEFAULT ''")
    if "note" not in tx_cols:
        conn.execute("ALTER TABLE store_transactions ADD COLUMN note TEXT DEFAULT ''")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_store_orders_capture ON store_orders(paypal_capture_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_store_transactions_type_external "
        "ON store_transactions(transaction_type, external_id)"
    )
    with contextlib.suppress(sqlite3.IntegrityError):
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_store_transactions_type_external_unique "
            "ON store_transactions(transaction_type, external_id) "
            "WHERE external_id IS NOT NULL AND external_id != ''"
        )
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# PAYPAL API HELPERS
# ---------------------------------------------------------------------------

_paypal_token_cache = {"token": None, "expires": 0}

def get_paypal_token():
    """Get PayPal OAuth2 access token (cached)."""
    if _paypal_token_cache["token"] and time.time() < _paypal_token_cache["expires"]:
        return _paypal_token_cache["token"]

    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        raise ValueError("PayPal credentials not configured")

    api_base = PAYPAL_API.get(PAYPAL_MODE, PAYPAL_API["sandbox"])

    resp = requests.post(
        f"{api_base}/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json"},
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    _paypal_token_cache["token"] = data["access_token"]
    _paypal_token_cache["expires"] = time.time() + data.get("expires_in", 3600) - 60

    return _paypal_token_cache["token"]


def paypal_request(method: str, endpoint: str, data: dict = None):
    """Make authenticated PayPal API request."""
    token = get_paypal_token()
    api_base = PAYPAL_API.get(PAYPAL_MODE, PAYPAL_API["sandbox"])

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    resp = requests.request(
        method,
        f"{api_base}{endpoint}",
        headers=headers,
        json=data,
        timeout=30
    )

    return resp


def create_paypal_order(package_id: str, order_id: str) -> dict:
    """Create a PayPal order for checkout."""
    package = PACKAGES.get(package_id)
    if not package:
        raise ValueError(f"Unknown package: {package_id}")

    order_data = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": order_id,
            "description": package["description"],
            "amount": {
                "currency_code": "USD",
                "value": f"{package['price_usd']:.2f}"
            }
        }],
        "application_context": {
            "brand_name": "BoTTube",
            "landing_page": "NO_PREFERENCE",
            "user_action": "PAY_NOW",
            "return_url": RETURN_URL,
            "cancel_url": CANCEL_URL
        }
    }

    resp = paypal_request("POST", "/v2/checkout/orders", order_data)
    resp.raise_for_status()
    return resp.json()


def capture_paypal_order(paypal_order_id: str) -> dict:
    """Capture (finalize) a PayPal payment."""
    resp = paypal_request("POST", f"/v2/checkout/orders/{paypal_order_id}/capture")
    resp.raise_for_status()
    return resp.json()

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def get_db():
    """Get database connection from Flask g context."""
    if not hasattr(g, 'db') or g.db is None:
        db_path = os.environ.get("BOTTUBE_DB_PATH", "/root/bottube/bottube.db")
        g.db = sqlite3.connect(db_path, timeout=30)
        g.db.execute("PRAGMA busy_timeout = 30000")
        g.db.row_factory = sqlite3.Row
    return g.db


def generate_order_id() -> str:
    """Generate unique order ID."""
    return f"ord_{secrets.token_hex(12)}"


def _request_json_object():
    """Parse the request body as a JSON object, or return a 400 error response."""
    data = request.get_json(silent=True)
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, (jsonify({"error": "JSON object required"}), 400)
    return data, None


def _optional_string_field(data: dict, field_name: str):
    """Extract and trim an optional string field, or return a 400 error if the type is wrong."""
    value = data.get(field_name)
    if value is None:
        return "", None
    if not isinstance(value, str):
        return None, (jsonify({"error": f"{field_name} must be a string"}), 400)
    return value.strip(), None


def _optional_int_field(data: dict, field_name: str):
    """Extract an optional positive-int field, or return a 400 error if invalid."""
    value = data.get(field_name)
    if value is None:
        return None, None
    if isinstance(value, bool) or not isinstance(value, int):
        return None, (jsonify({"error": f"{field_name} must be an integer"}), 400)
    if value <= 0:
        return None, (jsonify({"error": f"{field_name} must be a positive integer"}), 400)
    return value, None


_COMPLETABLE_ORDER_STATUSES = ("pending", "approved")
_REFUNDED_ORDER_STATUSES = ("partially_refunded", "refunded")
_REFUNDABLE_ORDER_STATUSES = ("completed", "partially_refunded")
_MAX_REFUND_CAS_ATTEMPTS = 4


def _to_usd(value) -> Decimal:
    """Quantize a finite value to 2 decimal places (USD cents)."""
    if isinstance(value, bool):
        raise TypeError("USD amount must not be a boolean")
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise InvalidOperation("USD amount must be finite")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_rtc(value) -> Decimal:
    """Quantize a finite value to 6 decimal places (RTC's smallest unit)."""
    if isinstance(value, bool):
        raise TypeError("RTC amount must not be a boolean")
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise InvalidOperation("RTC amount must be finite")
    return amount.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _extract_str(value) -> str:
    """Return a trimmed string value, or empty string for non-strings."""
    return value.strip() if isinstance(value, str) else ""


def _parse_usd_amount(amount_obj):
    """Parse a positive finite USD amount dict, returning None on invalid/non-USD values."""
    if not isinstance(amount_obj, dict):
        return None
    currency = amount_obj.get("currency_code")
    if currency is not None and (not isinstance(currency, str) or currency.strip().upper() != "USD"):
        return None
    value = amount_obj.get("value")
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = _to_usd(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extract_capture_details(payload: dict):
    """Pull the first capture id and captured USD amount out of a PayPal order/webhook payload."""
    capture_id = ""
    amount_usd = None
    if not isinstance(payload, dict):
        return capture_id, amount_usd
    purchase_units = payload.get("purchase_units")
    if not isinstance(purchase_units, list):
        return capture_id, amount_usd
    for purchase_unit in purchase_units:
        if not isinstance(purchase_unit, dict):
            continue
        payments = purchase_unit.get("payments")
        captures = payments.get("captures") if isinstance(payments, dict) else None
        if not isinstance(captures, list):
            continue
        for capture in captures:
            if not isinstance(capture, dict):
                continue
            capture_id = _extract_str(capture.get("id")) or capture_id
            amount_usd = _parse_usd_amount(capture.get("amount"))
            if capture_id:
                return capture_id, amount_usd
    return capture_id, amount_usd


def _record_store_transaction(
    db,
    *,
    order_id: str,
    agent_id=None,
    package_id: str,
    amount_usd: Decimal,
    rtc_credited: Decimal,
    transaction_type: str,
    external_id: str = "",
    note: str = "",
) -> bool:
    """Insert a store transaction row, deduped by (transaction_type, external_id); returns False if already recorded."""
    if external_id:
        existing = db.execute(
            """
            SELECT id FROM store_transactions
            WHERE transaction_type = ? AND external_id = ?
            """,
            (transaction_type, external_id),
        ).fetchone()
        if existing:
            return False

    try:
        db.execute(
            """
            INSERT INTO store_transactions
                (order_id, agent_id, package_id, amount_usd, rtc_credited,
                 transaction_type, external_id, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                agent_id,
                package_id,
                float(amount_usd),
                float(rtc_credited),
                transaction_type,
                external_id,
                note,
                int(time.time()),
            ),
        )
    except sqlite3.IntegrityError:
        if external_id:
            return False
        raise
    return True


def credit_rtc_to_agent(db, agent_id: int, amount: Decimal, reason: str) -> None:
    """Credit RTC to the live BoTTube wallet ledger."""
    db.execute(
        "UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?",
        (float(amount), agent_id),
    )
    db.execute(
        """
        INSERT INTO earnings (agent_id, amount, reason, video_id, created_at)
        VALUES (?, ?, ?, '', ?)
        """,
        (agent_id, float(amount), reason, time.time()),
    )


def debit_rtc_from_agent(db, agent_id: int, amount: Decimal, reason: str) -> None:
    """Reverse RTC from the live BoTTube wallet ledger."""
    db.execute(
        "UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?",
        (float(amount), agent_id),
    )
    db.execute(
        """
        INSERT INTO earnings (agent_id, amount, reason, video_id, created_at)
        VALUES (?, ?, ?, '', ?)
        """,
        (agent_id, float(-amount), reason, time.time()),
    )


def _complete_order_conflict_result(db, order_id: str):
    """Inspect current persisted status when an atomic completion claim loses a race."""
    row = db.execute(
        "SELECT status FROM store_orders WHERE id = ?",
        (order_id,),
    ).fetchone()
    current_status = row[0] if row else ""
    if current_status == "completed":
        return True, "already_completed"
    if current_status in _REFUNDED_ORDER_STATUSES:
        return False, "already_refunded"
    return False, "order_not_completable"


def _validate_capture_amount(order_amount: Decimal, capture_amount_usd, require_amount: bool) -> bool:
    """Verify capture amount matches the expected USD order amount."""
    if capture_amount_usd is None:
        return not require_amount
    try:
        normalized = _to_usd(capture_amount_usd)
    except (InvalidOperation, TypeError, ValueError):
        return False
    return normalized == order_amount


def _complete_order(
    db,
    order,
    *,
    capture_id: str,
    capture_amount_usd=None,
    require_amount: bool = False,
):
    """Mark an order completed and credit RTC atomically, idempotently keyed on the PayPal capture id."""
    order_amount = _to_usd(order["amount_usd"])
    rtc_amount = _to_rtc(order["rtc_amount"])
    if not _validate_capture_amount(order_amount, capture_amount_usd, require_amount):
        return False, "capture_amount_mismatch"

    if order["status"] == "completed":
        return True, "already_completed"
    if order["status"] in _REFUNDED_ORDER_STATUSES:
        return False, "already_refunded"
    if order["status"] not in _COMPLETABLE_ORDER_STATUSES:
        return False, "order_not_completable"

    cur = db.execute(
        """
        UPDATE store_orders
        SET status = 'completed', completed_at = ?, paypal_capture_id = ?
        WHERE id = ? AND status IN ('pending', 'approved')
        """,
        (int(time.time()), capture_id, order["id"]),
    )
    if cur.rowcount != 1:
        return _complete_order_conflict_result(db, order["id"])

    recorded = _record_store_transaction(
        db,
        order_id=order["id"],
        agent_id=order["agent_id"],
        package_id=order["package_id"],
        amount_usd=order_amount,
        rtc_credited=rtc_amount,
        transaction_type="purchase",
        external_id=capture_id,
        note="paypal_capture",
    )
    if not recorded:
        db.rollback()
        existing = db.execute(
            """
            SELECT order_id FROM store_transactions
            WHERE transaction_type = 'purchase' AND external_id = ?
            """,
            (capture_id,),
        ).fetchone()
        if existing and existing[0] == order["id"]:
            return True, "already_completed"
        return False, "duplicate_capture_id"

    if order["agent_id"]:
        credit_rtc_to_agent(
            db,
            int(order["agent_id"]),
            rtc_amount,
            f"store_purchase:{order['package_id']}",
        )

    db.commit()
    return True, "completed"


def _compute_refund_rtc(
    db,
    order_id: str,
    rtc_total: Decimal,
    order_amount: Decimal,
    applied_refund: Decimal,
) -> Decimal:
    """Compute proportional RTC reversal capped so cumulative refunds never exceed rtc_total."""
    raw_refund = ((rtc_total * applied_refund) / order_amount).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    row = db.execute(
        """
        SELECT COALESCE(SUM(-rtc_credited), 0)
        FROM store_transactions
        WHERE order_id = ? AND transaction_type = 'refund'
        """,
        (order_id,),
    ).fetchone()
    already_debited = _to_rtc(row[0] if row and row[0] is not None else 0)
    remaining_rtc = max(Decimal("0.000000"), rtc_total - already_debited)
    return min(raw_refund, remaining_rtc)


def _refund_id_exists(db, refund_id: str) -> bool:
    """Return True if a refund transaction with this external_id is already recorded."""
    if not refund_id:
        return False
    return bool(
        db.execute(
            "SELECT id FROM store_transactions WHERE transaction_type = 'refund' AND external_id = ?",
            (refund_id,),
        ).fetchone()
    )


def _attempt_refund_order(
    db,
    order_id: str,
    *,
    refund_id: str,
    requested_refund: Decimal,
    note: str,
):
    """Run one compare-and-set refund attempt against live order state; returns None to retry."""
    live = db.execute(
        """
        SELECT id, agent_id, package_id, amount_usd, rtc_amount, status, refund_amount_usd
        FROM store_orders
        WHERE id = ?
        """,
        (order_id,),
    ).fetchone()
    if not live:
        return False, "order_not_found"

    live_id, agent_id, package_id, raw_amount_usd, raw_rtc_amount, status, raw_refunded = (
        live[0], live[1], live[2], live[3], live[4], live[5], live[6]
    )
    if status == "refunded" or _refund_id_exists(db, refund_id):
        return True, "already_refunded"
    if status not in _REFUNDABLE_ORDER_STATUSES:
        return False, "order_not_refundable"

    order_amount = _to_usd(raw_amount_usd)
    if order_amount <= 0:
        return False, "invalid_order_amount"
    already_refunded = _to_usd(raw_refunded or 0)
    applied_refund = min(requested_refund, max(Decimal("0.00"), order_amount - already_refunded))
    if applied_refund <= 0:
        return True, "already_refunded"

    new_refunded_total = already_refunded + applied_refund
    new_status = "refunded" if new_refunded_total >= order_amount else "partially_refunded"

    cur = db.execute(
        """
        UPDATE store_orders
        SET status = ?, refund_amount_usd = ?, refunded_at = ?
        WHERE id = ?
          AND status = ?
          AND ROUND(COALESCE(refund_amount_usd, 0), 2) = ?
        """,
        (
            new_status,
            float(new_refunded_total),
            int(time.time()),
            live_id,
            status,
            float(already_refunded),
        ),
    )
    if cur.rowcount != 1:
        return None

    rtc_total = _to_rtc(raw_rtc_amount)
    rtc_refund = _compute_refund_rtc(db, live_id, rtc_total, order_amount, applied_refund)
    recorded = _record_store_transaction(
        db,
        order_id=live_id,
        agent_id=agent_id,
        package_id=package_id,
        amount_usd=applied_refund,
        rtc_credited=-rtc_refund,
        transaction_type="refund",
        external_id=refund_id,
        note=note or "paypal_refund",
    )
    if not recorded:
        db.rollback()
        return True, "already_refunded"

    if agent_id and rtc_refund > 0:
        debit_rtc_from_agent(
            db,
            int(agent_id),
            rtc_refund,
            f"store_refund:{package_id}",
        )

    db.commit()
    return True, new_status


def _refund_order(
    db,
    order,
    *,
    refund_id: str,
    refund_amount_usd: Decimal,
    note: str = "",
):
    """Apply a (possibly partial) refund atomically, debiting RTC proportionally and idempotent on refund_id."""
    try:
        requested_refund = _to_usd(refund_amount_usd)
    except (InvalidOperation, TypeError, ValueError):
        return False, "invalid_refund_amount"
    if requested_refund <= 0:
        return False, "invalid_refund_amount"

    for _ in range(_MAX_REFUND_CAS_ATTEMPTS):
        result = _attempt_refund_order(
            db,
            order["id"],
            refund_id=refund_id,
            requested_refund=requested_refund,
            note=note,
        )
        if result is not None:
            return result
    return False, "refund_conflict"


def verify_paypal_webhook_signature(headers, event: dict) -> tuple[bool, str]:
    """Verify a PayPal webhook using PayPal's own verification endpoint."""
    if not PAYPAL_WEBHOOK_ID:
        return False, "webhook_not_configured"

    required_headers = {
        "transmission_id": headers.get("PAYPAL-TRANSMISSION-ID", ""),
        "transmission_time": headers.get("PAYPAL-TRANSMISSION-TIME", ""),
        "transmission_sig": headers.get("PAYPAL-TRANSMISSION-SIG", ""),
        "cert_url": headers.get("PAYPAL-CERT-URL", ""),
        "auth_algo": headers.get("PAYPAL-AUTH-ALGO", ""),
    }
    if not all(required_headers.values()):
        return False, "missing_signature_headers"

    payload = {
        **required_headers,
        "webhook_id": PAYPAL_WEBHOOK_ID,
        "webhook_event": event,
    }
    try:
        resp = paypal_request("POST", "/v1/notifications/verify-webhook-signature", payload)
        resp.raise_for_status()
        body = resp.json()
    except requests.RequestException:
        return False, "verification_request_failed"

    if body.get("verification_status") != "SUCCESS":
        return False, "invalid_signature"
    return True, "verified"

# ---------------------------------------------------------------------------
# API ENDPOINTS
# ---------------------------------------------------------------------------

@store_bp.route("/packages", methods=["GET"])
def list_packages():
    """List available packages.

    GET /api/store/packages

    Returns list of purchasable packages with prices and contents.
    """
    packages_list = []
    for pkg_id, pkg in PACKAGES.items():
        packages_list.append({
            "id": pkg_id,
            "name": pkg["name"],
            "description": pkg["description"],
            "price_usd": pkg["price_usd"],
            "rtc_credits": pkg["rtc_credits"],
            "video_generations": pkg["video_generations"],
            "gpu_minutes": pkg["gpu_minutes"],
        })

    return jsonify({
        "ok": True,
        "packages": packages_list,
        "currency": "USD",
        "payment_methods": ["paypal"]
    })


@store_bp.route("/checkout", methods=["POST"])
def create_checkout():
    """Start checkout for a package.

    POST /api/store/checkout
    {
        "package_id": "creator",
        "agent_id": 123,        // Optional - if logged in
        "email": "user@example.com"  // For guest checkout
    }

    Returns PayPal approval URL to redirect user to.
    """
    data, error = _request_json_object()
    if error:
        return error
    package_id, error = _optional_string_field(data, "package_id")
    if error:
        return error
    agent_id, error = _optional_int_field(data, "agent_id")
    if error:
        return error
    email, error = _optional_string_field(data, "email")
    if error:
        return error

    if not package_id:
        return jsonify({"error": "package_id required"}), 400

    if package_id not in PACKAGES:
        return jsonify({"error": f"Unknown package: {package_id}"}), 400

    if not agent_id and not email:
        return jsonify({"error": "agent_id or email required"}), 400

    package = PACKAGES[package_id]
    order_id = generate_order_id()

    try:
        # Create PayPal order
        paypal_order = create_paypal_order(package_id, order_id)
        paypal_order_id = paypal_order["id"]

        # Find approval URL
        approval_url = None
        for link in paypal_order.get("links", []):
            if link.get("rel") == "approve":
                approval_url = link["href"]
                break

        if not approval_url:
            return jsonify({"error": "Failed to get PayPal approval URL"}), 500

        # Save order to database
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO store_orders
            (id, agent_id, email, package_id, amount_usd, rtc_amount, paypal_order_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            order_id,
            agent_id,
            email,
            package_id,
            package["price_usd"],
            package["rtc_credits"],
            paypal_order_id,
            int(time.time())
        ))
        db.commit()

        return jsonify({
            "ok": True,
            "order_id": order_id,
            "paypal_order_id": paypal_order_id,
            "approval_url": approval_url,
            "package": {
                "name": package["name"],
                "price_usd": package["price_usd"],
                "rtc_credits": package["rtc_credits"]
            }
        })

    except requests.RequestException:
        return jsonify({"error": "PayPal API error"}), 500
    except Exception:
        return jsonify({"error": "Checkout failed"}), 500


def _capture_precheck_redirect(row):
    """Return an early redirect URL when an order is already terminal or non-completable."""
    if not row:
        return f"{BASE_URL}/store?error=order_not_found"
    if row["status"] == "completed":
        return f"{BASE_URL}/store?success=1&order={row['id']}"
    if row["status"] in _REFUNDED_ORDER_STATUSES:
        return f"{BASE_URL}/store?error=already_refunded"
    if row["status"] not in _COMPLETABLE_ORDER_STATUSES:
        return f"{BASE_URL}/store?error=order_not_completable"
    return None


def _mark_order_failed_if_pending(db, order_id: str) -> None:
    """Mark an order failed only if it has not already transitioned out of pending/approved."""
    db.execute(
        "UPDATE store_orders SET status = 'failed' WHERE id = ? AND status IN ('pending', 'approved')",
        (order_id,),
    )
    db.commit()


@store_bp.route("/capture", methods=["GET"])
def capture_payment():
    """Capture payment after PayPal approval.

    This is the return URL PayPal redirects to after user approves.

    GET /api/store/capture?token=PAYPAL_ORDER_ID

    Captures payment and credits RTC to user's account.
    """
    paypal_order_id = request.args.get("token")

    if not paypal_order_id:
        return redirect(f"{BASE_URL}/store?error=missing_token")

    db = get_db()
    row = db.execute(
        """
        SELECT *
        FROM store_orders
        WHERE paypal_order_id = ?
        """,
        (paypal_order_id,),
    ).fetchone()

    early_redirect = _capture_precheck_redirect(row)
    if early_redirect:
        return redirect(early_redirect)

    try:
        capture_result = capture_paypal_order(paypal_order_id)
        if not isinstance(capture_result, dict) or capture_result.get("status") != "COMPLETED":
            _mark_order_failed_if_pending(db, row["id"])
            return redirect(f"{BASE_URL}/store?error=payment_failed")

        capture_id, capture_amount = _extract_capture_details(capture_result)
        ok, reason = _complete_order(
            db,
            row,
            capture_id=capture_id,
            capture_amount_usd=capture_amount,
            require_amount=True,
        )
        if not ok:
            _mark_order_failed_if_pending(db, row["id"])
            return redirect(f"{BASE_URL}/store?error={reason}")

        return redirect(f"{BASE_URL}/store?success=1&order={row['id']}&rtc={row['rtc_amount']}")

    except requests.RequestException:
        return redirect(f"{BASE_URL}/store?error=paypal_error")
    except Exception:
        return redirect(f"{BASE_URL}/store?error=processing_error")


@store_bp.route("/order/<order_id>", methods=["GET"])
def get_order(order_id):
    """Get order status.

    GET /api/store/order/ord_xxxxx
    """
    db = get_db()
    row = db.execute(
        """
        SELECT id, agent_id, email, package_id, amount_usd, rtc_amount,
               status, created_at, completed_at, refund_amount_usd, refunded_at
        FROM store_orders
        WHERE id = ?
        """,
        (order_id,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Order not found"}), 404

    return jsonify({
        "ok": True,
        "order": {
            "id": row[0],
            "agent_id": row[1],
            "email": row[2],
            "package_id": row[3],
            "amount_usd": row[4],
            "rtc_amount": row[5],
            "status": row[6],
            "created_at": row[7],
            "completed_at": row[8],
            "refund_amount_usd": row[9],
            "refunded_at": row[10],
        }
    })


@store_bp.route("/stats", methods=["GET"])
def store_stats():
    """Get store statistics (admin only).

    GET /api/store/stats
    X-Admin-Key: required
    """
    admin_key = request.headers.get("X-Admin-Key", "")
    expected_key = os.environ.get("BOTTUBE_ADMIN_KEY", "")

    if not admin_key or not expected_key or not hmac.compare_digest(
        admin_key.encode("utf-8"), expected_key.encode("utf-8")
    ):
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()
    cur = db.cursor()

    # Total sales
    cur.execute("""
        SELECT COUNT(*), SUM(amount_usd), SUM(rtc_amount)
        FROM store_orders
        WHERE status = 'completed'
    """)
    total_orders, total_usd, total_rtc = cur.fetchone()

    # Sales by package
    cur.execute("""
        SELECT package_id, COUNT(*), SUM(amount_usd)
        FROM store_orders
        WHERE status = 'completed'
        GROUP BY package_id
    """)
    by_package = {row[0]: {"count": row[1], "usd": row[2]} for row in cur.fetchall()}

    # Recent orders
    cur.execute("""
        SELECT id, package_id, amount_usd, status, created_at
        FROM store_orders
        ORDER BY created_at DESC
        LIMIT 10
    """)
    recent = [
        {"id": r[0], "package": r[1], "usd": r[2], "status": r[3], "created_at": r[4]}
        for r in cur.fetchall()
    ]

    return jsonify({
        "ok": True,
        "stats": {
            "total_orders": total_orders or 0,
            "total_usd": total_usd or 0,
            "total_rtc_sold": total_rtc or 0,
            "by_package": by_package,
            "recent_orders": recent
        }
    })


# ---------------------------------------------------------------------------
# WEBHOOK (Optional - for async notifications)
# ---------------------------------------------------------------------------

def _related_ids(resource: dict) -> dict:
    """Safely extract supplementary_data.related_ids as a dict."""
    supp = resource.get("supplementary_data")
    related = supp.get("related_ids") if isinstance(supp, dict) else None
    return related if isinstance(related, dict) else {}


def _handle_capture_completed_webhook(db, resource: dict) -> None:
    """Process a verified PAYMENT.CAPTURE.COMPLETED webhook resource."""
    capture_id = _extract_str(resource.get("id"))
    order_id = _extract_str(_related_ids(resource).get("order_id"))
    order = None
    if order_id:
        order = db.execute("SELECT * FROM store_orders WHERE paypal_order_id = ?", (order_id,)).fetchone()
    if not order and capture_id:
        order = db.execute("SELECT * FROM store_orders WHERE paypal_capture_id = ?", (capture_id,)).fetchone()
    if not order:
        return
    capture_amount = _parse_usd_amount(resource.get("amount"))
    _complete_order(
        db,
        order,
        capture_id=capture_id,
        capture_amount_usd=capture_amount,
        require_amount=True,
    )


def _handle_capture_refunded_webhook(db, resource: dict) -> None:
    """Process a verified PAYMENT.CAPTURE.REFUNDED webhook resource."""
    related = _related_ids(resource)
    refund_id = _extract_str(resource.get("id"))
    capture_id = (
        _extract_str(resource.get("sale_id"))
        or _extract_str(resource.get("capture_id"))
        or _extract_str(related.get("capture_id"))
    )
    order = None
    if capture_id:
        order = db.execute("SELECT * FROM store_orders WHERE paypal_capture_id = ?", (capture_id,)).fetchone()
    if not order:
        order_id = _extract_str(related.get("order_id"))
        if order_id:
            order = db.execute("SELECT * FROM store_orders WHERE paypal_order_id = ?", (order_id,)).fetchone()
    if not order:
        return

    refund_amount = _parse_usd_amount(resource.get("amount"))
    if refund_amount is None:
        return
    _refund_order(
        db,
        order,
        refund_id=refund_id,
        refund_amount_usd=refund_amount,
        note=_extract_str(resource.get("status")) or "paypal_refund",
    )


@store_bp.route("/webhook/paypal", methods=["POST"])
def paypal_webhook():
    """Handle PayPal webhooks for payment events.

    POST /api/store/webhook/paypal

    Handles events like PAYMENT.CAPTURE.COMPLETED, PAYMENT.CAPTURE.REFUNDED
    """
    event, error = _request_json_object()
    if error:
        return error
    verified, reason = verify_paypal_webhook_signature(request.headers, event)
    if not verified:
        return jsonify({"error": "invalid_webhook", "reason": reason}), 401

    event_type = event.get("event_type", "")
    if not isinstance(event_type, str):
        return jsonify({"error": "event_type must be a string"}), 400
    resource = event.get("resource")
    if resource is None:
        resource = {}
    if not isinstance(resource, dict):
        return jsonify({"error": "resource must be an object"}), 400

    db = get_db()
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        _handle_capture_completed_webhook(db, resource)
    elif event_type == "PAYMENT.CAPTURE.REFUNDED":
        _handle_capture_refunded_webhook(db, resource)

    return jsonify({"ok": True})


if __name__ == "__main__":
    # Test mode - show packages
    print("BoTTube Package Store")
    print("=" * 50)
    for pkg_id, pkg in PACKAGES.items():
        print(f"\n{pkg['name']} (${pkg['price_usd']:.2f})")
        print(f"  - {pkg['rtc_credits']} RTC credits")
        print(f"  - {pkg['video_generations']} video generations")
        print(f"  - {pkg['gpu_minutes']} GPU minutes")
