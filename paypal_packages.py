#!/usr/bin/env python3
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

import os
import secrets
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import requests
from flask import Blueprint, request, jsonify, g, redirect

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
        "description": "5 AI video generations + 250 RTC credits",
        "price_usd": 5.00,
        "rtc_credits": 250,
        "video_generations": 5,
        "gpu_minutes": 10,
    },
    "creator": {
        "name": "Creator Pack",
        "description": "20 AI video generations + 1000 RTC credits",
        "price_usd": 15.00,
        "rtc_credits": 1000,
        "video_generations": 20,
        "gpu_minutes": 45,
    },
    "studio": {
        "name": "Studio Pack",
        "description": "100 AI video generations + 5000 RTC credits",
        "price_usd": 50.00,
        "rtc_credits": 5000,
        "video_generations": 100,
        "gpu_minutes": 200,
    },
    "enterprise": {
        "name": "Enterprise Pack",
        "description": "500 AI video generations + 25000 RTC credits",
        "price_usd": 200.00,
        "rtc_credits": 25000,
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

    import sqlite3
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
        import sqlite3
        db_path = os.environ.get("BOTTUBE_DB_PATH", "/root/bottube/bottube.db")
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


def generate_order_id() -> str:
    """Generate unique order ID."""
    return f"ord_{secrets.token_hex(12)}"


def _to_usd(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_rtc(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _extract_capture_details(payload: dict):
    capture_id = ""
    amount_usd = None
    for purchase_unit in payload.get("purchase_units", []):
        captures = (purchase_unit.get("payments") or {}).get("captures") or []
        for capture in captures:
            capture_id = capture.get("id", "") or capture_id
            value = ((capture.get("amount") or {}).get("value"))
            if value not in (None, ""):
                try:
                    amount_usd = _to_usd(value)
                except (InvalidOperation, TypeError, ValueError):
                    amount_usd = None
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


def _complete_order(db, order, *, capture_id: str, capture_amount_usd=None):
    order_amount = _to_usd(order["amount_usd"])
    rtc_amount = _to_rtc(order["rtc_amount"])
    if capture_amount_usd is not None and capture_amount_usd != order_amount:
        return False, "capture_amount_mismatch"

    if order["status"] == "completed":
        return True, "already_completed"

    if capture_id:
        existing = db.execute(
            """
            SELECT id FROM store_transactions
            WHERE transaction_type = 'purchase' AND external_id = ?
            """,
            (capture_id,),
        ).fetchone()
        if existing:
            return True, "already_completed"

    db.execute(
        """
        UPDATE store_orders
        SET status = 'completed', completed_at = ?, paypal_capture_id = ?
        WHERE id = ?
        """,
        (int(time.time()), capture_id, order["id"]),
    )

    if order["agent_id"]:
        credit_rtc_to_agent(
            db,
            int(order["agent_id"]),
            rtc_amount,
            f"store_purchase:{order['package_id']}",
        )

    _record_store_transaction(
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
    db.commit()
    return True, "completed"


def _refund_order(
    db,
    order,
    *,
    refund_id: str,
    refund_amount_usd: Decimal,
    note: str = "",
):
    if refund_id:
        existing = db.execute(
            """
            SELECT id FROM store_transactions
            WHERE transaction_type = 'refund' AND external_id = ?
            """,
            (refund_id,),
        ).fetchone()
        if existing:
            return True, "already_refunded"

    order_amount = _to_usd(order["amount_usd"])
    already_refunded = _to_usd(order["refund_amount_usd"] or 0)
    remaining = max(Decimal("0.00"), order_amount - already_refunded)
    refund_amount_usd = min(refund_amount_usd, remaining)
    if refund_amount_usd <= 0:
        return True, "already_refunded"

    rtc_total = _to_rtc(order["rtc_amount"])
    rtc_refund = (
        (rtc_total * refund_amount_usd) / order_amount
    ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    new_refunded_total = already_refunded + refund_amount_usd
    new_status = "refunded" if new_refunded_total >= order_amount else "partially_refunded"

    db.execute(
        """
        UPDATE store_orders
        SET status = ?, refund_amount_usd = ?, refunded_at = ?
        WHERE id = ?
        """,
        (new_status, float(new_refunded_total), int(time.time()), order["id"]),
    )

    if order["agent_id"] and rtc_refund > 0:
        debit_rtc_from_agent(
            db,
            int(order["agent_id"]),
            rtc_refund,
            f"store_refund:{order['package_id']}",
        )

    _record_store_transaction(
        db,
        order_id=order["id"],
        agent_id=order["agent_id"],
        package_id=order["package_id"],
        amount_usd=refund_amount_usd,
        rtc_credited=-rtc_refund,
        transaction_type="refund",
        external_id=refund_id,
        note=note or "paypal_refund",
    )
    db.commit()
    return True, new_status


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
    data = request.get_json() or {}
    package_id = data.get("package_id")
    agent_id = data.get("agent_id")
    email = data.get("email")

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

    except requests.RequestException as e:
        return jsonify({"error": f"PayPal API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

    if not row:
        return redirect(f"{BASE_URL}/store?error=order_not_found")

    if row["status"] == "completed":
        # Already processed
        return redirect(f"{BASE_URL}/store?success=1&order={row['id']}")

    try:
        capture_result = capture_paypal_order(paypal_order_id)
        if capture_result.get("status") != "COMPLETED":
            db.execute("UPDATE store_orders SET status = 'failed' WHERE id = ?", (row["id"],))
            db.commit()
            return redirect(f"{BASE_URL}/store?error=payment_failed")

        capture_id, capture_amount = _extract_capture_details(capture_result)
        ok, reason = _complete_order(
            db,
            row,
            capture_id=capture_id,
            capture_amount_usd=capture_amount,
        )
        if not ok:
            db.execute("UPDATE store_orders SET status = 'failed' WHERE id = ?", (row["id"],))
            db.commit()
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

    if not admin_key or admin_key != expected_key:
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

@store_bp.route("/webhook/paypal", methods=["POST"])
def paypal_webhook():
    """Handle PayPal webhooks for payment events.

    POST /api/store/webhook/paypal

    Handles events like PAYMENT.CAPTURE.COMPLETED, PAYMENT.CAPTURE.REFUNDED
    """
    event = request.get_json(silent=True) or {}
    verified, reason = verify_paypal_webhook_signature(request.headers, event)
    if not verified:
        return jsonify({"error": "invalid_webhook", "reason": reason}), 401

    event_type = event.get("event_type", "")
    resource = event.get("resource", {}) or {}
    db = get_db()

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        capture_id = resource.get("id", "")
        order_id = ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id", "")
        order = None
        if order_id:
            order = db.execute("SELECT * FROM store_orders WHERE paypal_order_id = ?", (order_id,)).fetchone()
        if not order and capture_id:
            order = db.execute("SELECT * FROM store_orders WHERE paypal_capture_id = ?", (capture_id,)).fetchone()
        if order:
            _, capture_amount = _extract_capture_details(
                {
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": capture_id,
                                        "amount": resource.get("amount") or {},
                                    }
                                ]
                            }
                        }
                    ]
                }
            )
            _complete_order(
                db,
                order,
                capture_id=capture_id,
                capture_amount_usd=capture_amount,
            )

    elif event_type == "PAYMENT.CAPTURE.REFUNDED":
        refund_id = resource.get("id", "")
        capture_id = (
            resource.get("sale_id")
            or resource.get("capture_id")
            or ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("capture_id", "")
        )
        order = None
        if capture_id:
            order = db.execute("SELECT * FROM store_orders WHERE paypal_capture_id = ?", (capture_id,)).fetchone()
        if not order:
            order_id = ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id", "")
            if order_id:
                order = db.execute("SELECT * FROM store_orders WHERE paypal_order_id = ?", (order_id,)).fetchone()

        if order:
            try:
                refund_amount = _to_usd((resource.get("amount") or {}).get("value", "0"))
            except (InvalidOperation, TypeError, ValueError):
                refund_amount = Decimal("0.00")
            _refund_order(
                db,
                order,
                refund_id=refund_id,
                refund_amount_usd=refund_amount,
                note=resource.get("status", "") or "paypal_refund",
            )

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
