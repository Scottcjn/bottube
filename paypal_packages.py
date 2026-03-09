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

import json
import os
import secrets
import time
from functools import wraps

import requests
from flask import Blueprint, request, jsonify, g, redirect

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")  # sandbox or live

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
    status TEXT DEFAULT 'pending',  -- pending, approved, completed, cancelled, refunded
    created_at INTEGER NOT NULL,
    completed_at INTEGER,
    paypal_capture_id TEXT,
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
    created_at INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES store_orders(id)
);

CREATE INDEX IF NOT EXISTS idx_store_orders_status ON store_orders(status);
CREATE INDEX IF NOT EXISTS idx_store_orders_agent ON store_orders(agent_id);
CREATE INDEX IF NOT EXISTS idx_store_orders_paypal ON store_orders(paypal_order_id);
"""

def init_store_db(db_path: str = None):
    """Initialize store tables in the database."""
    if db_path is None:
        db_path = "/root/bottube/bottube.db"

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.executescript(STORE_SCHEMA)
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# PAYPAL API HELPERS
# ---------------------------------------------------------------------------

_paypal_token_cache = {"token": None, "expires": 0}

def get_paypal_token():
    """Get PayPal OAuth2 access token (cached)."""
    global _paypal_token_cache

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


def credit_rtc_to_agent(agent_id: int, amount: float, memo: str = "Package purchase"):
    """Credit RTC to an agent's balance."""
    db = get_db()
    cur = db.cursor()

    # Update or insert balance
    cur.execute("""
        INSERT INTO agent_balances (agent_id, rtc_balance, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(agent_id) DO UPDATE SET
            rtc_balance = rtc_balance + ?,
            updated_at = ?
    """, (agent_id, amount, int(time.time()), amount, int(time.time())))

    # Log the transaction
    cur.execute("""
        INSERT INTO rtc_transactions (agent_id, amount, tx_type, memo, created_at)
        VALUES (?, ?, 'credit', ?, ?)
    """, (agent_id, amount, memo, int(time.time())))

    db.commit()

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
    cur = db.cursor()

    # Find our order
    cur.execute("""
        SELECT id, agent_id, email, package_id, rtc_amount, status
        FROM store_orders
        WHERE paypal_order_id = ?
    """, (paypal_order_id,))
    row = cur.fetchone()

    if not row:
        return redirect(f"{BASE_URL}/store?error=order_not_found")

    order_id, agent_id, email, package_id, rtc_amount, status = row

    if status == "completed":
        # Already processed
        return redirect(f"{BASE_URL}/store?success=1&order={order_id}")

    try:
        # Capture the payment
        capture_result = capture_paypal_order(paypal_order_id)
        capture_status = capture_result.get("status")

        if capture_status != "COMPLETED":
            cur.execute("""
                UPDATE store_orders SET status = 'failed' WHERE id = ?
            """, (order_id,))
            db.commit()
            return redirect(f"{BASE_URL}/store?error=payment_failed")

        # Get capture ID
        capture_id = None
        for pu in capture_result.get("purchase_units", []):
            for cap in pu.get("payments", {}).get("captures", []):
                capture_id = cap.get("id")
                break

        # Update order status
        cur.execute("""
            UPDATE store_orders
            SET status = 'completed', completed_at = ?, paypal_capture_id = ?
            WHERE id = ?
        """, (int(time.time()), capture_id, order_id))

        # Credit RTC to agent
        if agent_id:
            credit_rtc_to_agent(agent_id, rtc_amount, f"Package purchase: {package_id}")

        # Log transaction
        cur.execute("""
            INSERT INTO store_transactions
            (order_id, agent_id, package_id, amount_usd, rtc_credited, transaction_type, created_at)
            VALUES (?, ?, ?, ?, ?, 'purchase', ?)
        """, (
            order_id,
            agent_id,
            package_id,
            PACKAGES[package_id]["price_usd"],
            rtc_amount,
            int(time.time())
        ))

        db.commit()

        return redirect(f"{BASE_URL}/store?success=1&order={order_id}&rtc={rtc_amount}")

    except requests.RequestException as e:
        return redirect(f"{BASE_URL}/store?error=paypal_error")
    except Exception as e:
        return redirect(f"{BASE_URL}/store?error=processing_error")


@store_bp.route("/order/<order_id>", methods=["GET"])
def get_order(order_id):
    """Get order status.

    GET /api/store/order/ord_xxxxx
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        SELECT id, agent_id, email, package_id, amount_usd, rtc_amount,
               status, created_at, completed_at
        FROM store_orders
        WHERE id = ?
    """, (order_id,))
    row = cur.fetchone()

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
            "completed_at": row[8]
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
    # TODO: Verify webhook signature
    # https://developer.paypal.com/docs/api/webhooks/v1/#verify-webhook-signature

    event = request.get_json()
    event_type = event.get("event_type", "")

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        # Payment completed - could be used for async processing
        resource = event.get("resource", {})
        capture_id = resource.get("id")
        # Already handled in capture endpoint
        pass

    elif event_type == "PAYMENT.CAPTURE.REFUNDED":
        # Handle refund
        resource = event.get("resource", {})
        # TODO: Deduct RTC from user's balance
        pass

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
