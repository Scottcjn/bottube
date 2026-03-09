"""
BoTTube Ergo (ERG) ↔ RTC Bridge
Flask Blueprint for exchanging public Ergo mainnet ERG for platform RTC credits.

Bidirectional bridge:
  - Deposit: User sends ERG to platform wallet → gets RTC credits
  - Withdraw: User spends RTC credits → receives ERG to their address

Uses Ergo Explorer API (api.ergoplatform.com) for transaction verification.
No local Ergo node required — all verification via public APIs.

Exchange rate: market-based or fixed by admin.
"""

from flask import Blueprint, request, jsonify, g, session
import hashlib
import json
import logging
import os
import sqlite3
import time
import urllib.request

ergo_bp = Blueprint("ergo_bridge", __name__)
log = logging.getLogger("ergo_bridge")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Platform ERG wallet address (mainnet)
ERGO_PLATFORM_ADDRESS = os.environ.get("ERGO_PLATFORM_ADDRESS", "")

# Exchange rate: 1 ERG = X RTC (default based on ERG ~$0.80, RTC ~$0.10)
ERG_TO_RTC_RATE = float(os.environ.get("ERG_TO_RTC_RATE", "8.0"))

# Fees
DEPOSIT_FEE_PERCENT = 1.0    # 1% fee on deposits
WITHDRAW_FEE_RTC = 0.5       # 0.5 RTC flat fee on withdrawals
MIN_DEPOSIT_ERG = 0.01       # Minimum 0.01 ERG deposit
MIN_WITHDRAW_RTC = 5.0       # Minimum 5 RTC to withdraw as ERG

# Ergo Explorer API
EXPLORER_API = "https://api.ergoplatform.com/api/v1"

# Admin key for management endpoints
ADMIN_KEY = os.environ.get("BOTTUBE_ADMIN_KEY", "bottube_admin_key_2026")

# Confirmation threshold (blocks)
REQUIRED_CONFIRMATIONS = 3


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    """Get database connection from Flask g."""
    if "db" not in g:
        db_path = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


def init_ergo_tables(db=None):
    """Create Ergo bridge tables if they don't exist."""
    if db is None:
        db_path = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")
        db = sqlite3.connect(db_path)
        should_close = True
    else:
        should_close = False

    db.executescript("""
        CREATE TABLE IF NOT EXISTS ergo_deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_id TEXT UNIQUE NOT NULL,
            from_address TEXT NOT NULL,
            amount_erg REAL NOT NULL,
            fee_erg REAL NOT NULL,
            net_erg REAL NOT NULL,
            rtc_credited REAL NOT NULL,
            agent_id INTEGER,
            confirmations INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at REAL NOT NULL,
            confirmed_at REAL DEFAULT 0,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );

        CREATE TABLE IF NOT EXISTS ergo_withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            amount_rtc REAL NOT NULL,
            fee_rtc REAL NOT NULL,
            net_rtc REAL NOT NULL,
            erg_amount REAL NOT NULL,
            to_address TEXT NOT NULL,
            tx_id TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at REAL NOT NULL,
            completed_at REAL DEFAULT 0,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );

        CREATE INDEX IF NOT EXISTS idx_ergo_dep_txid ON ergo_deposits(tx_id);
        CREATE INDEX IF NOT EXISTS idx_ergo_dep_status ON ergo_deposits(status);
        CREATE INDEX IF NOT EXISTS idx_ergo_wd_agent ON ergo_withdrawals(agent_id);
        CREATE INDEX IF NOT EXISTS idx_ergo_wd_status ON ergo_withdrawals(status);
    """)
    db.commit()
    if should_close:
        db.close()


# ---------------------------------------------------------------------------
# Ergo Explorer API helpers
# ---------------------------------------------------------------------------

def _explorer_get(path):
    """GET request to Ergo Explorer API."""
    url = f"{EXPLORER_API}{path}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.error(f"Explorer API error: {url} → {e}")
        return None


def verify_ergo_tx(tx_id):
    """Verify an Ergo transaction via the Explorer API.

    Returns dict with:
      - ok: bool
      - amount_erg: float (amount sent to platform address)
      - from_address: str
      - confirmations: int
      - error: str (if not ok)
    """
    if not ERGO_PLATFORM_ADDRESS:
        return {"ok": False, "error": "Platform ERG address not configured"}

    # Fetch transaction details
    tx_data = _explorer_get(f"/transactions/{tx_id}")
    if not tx_data:
        return {"ok": False, "error": "Transaction not found or Explorer API unavailable"}

    # Check confirmations
    confirmations = tx_data.get("numConfirmations", 0)

    # Find outputs to our platform address
    platform_amount_nanoerg = 0
    for output in tx_data.get("outputs", []):
        if output.get("address") == ERGO_PLATFORM_ADDRESS:
            platform_amount_nanoerg += output.get("value", 0)

    if platform_amount_nanoerg == 0:
        return {
            "ok": False,
            "error": f"No outputs found to platform address {ERGO_PLATFORM_ADDRESS[:20]}..."
        }

    # Convert nanoERG to ERG (1 ERG = 10^9 nanoERG)
    amount_erg = platform_amount_nanoerg / 1e9

    # Get sender address (first input)
    from_address = ""
    inputs = tx_data.get("inputs", [])
    if inputs:
        from_address = inputs[0].get("address", "")

    return {
        "ok": True,
        "amount_erg": round(amount_erg, 9),
        "from_address": from_address,
        "confirmations": confirmations,
        "tx_id": tx_id,
    }


def get_platform_erg_balance():
    """Get the platform wallet's ERG balance from Explorer."""
    if not ERGO_PLATFORM_ADDRESS:
        return {"error": "Platform address not configured"}

    data = _explorer_get(f"/addresses/{ERGO_PLATFORM_ADDRESS}/balance/confirmed")
    if not data:
        return {"error": "Could not fetch balance"}

    return {
        "address": ERGO_PLATFORM_ADDRESS,
        "balance_nanoerg": data.get("nanoErgs", 0),
        "balance_erg": round(data.get("nanoErgs", 0) / 1e9, 6),
    }


# ---------------------------------------------------------------------------
# RTC credit/debit helpers (uses bottube_server's award_rtc pattern)
# ---------------------------------------------------------------------------

def _award_rtc(db, agent_id, amount, reason):
    """Credit RTC to an agent's balance."""
    db.execute(
        "UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?",
        (amount, agent_id),
    )
    db.execute(
        "INSERT INTO earnings (agent_id, amount, source, created_at) VALUES (?, ?, ?, ?)",
        (agent_id, amount, reason, time.time()),
    )
    db.commit()


def _debit_rtc(db, agent_id, amount):
    """Debit RTC from an agent's balance. Returns True if sufficient funds."""
    row = db.execute(
        "SELECT rtc_balance FROM agents WHERE id = ?", (agent_id,)
    ).fetchone()
    if not row or row["rtc_balance"] < amount:
        return False
    db.execute(
        "UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?",
        (amount, agent_id),
    )
    db.commit()
    return True


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@ergo_bp.route("/api/ergo/info")
def ergo_info():
    """Public info about the ERG ↔ RTC bridge."""
    balance = get_platform_erg_balance()

    return jsonify({
        "platform_address": ERGO_PLATFORM_ADDRESS,
        "exchange_rate": {
            "erg_to_rtc": ERG_TO_RTC_RATE,
            "rtc_to_erg": round(1.0 / ERG_TO_RTC_RATE, 6) if ERG_TO_RTC_RATE > 0 else 0,
        },
        "fees": {
            "deposit_percent": DEPOSIT_FEE_PERCENT,
            "withdraw_flat_rtc": WITHDRAW_FEE_RTC,
        },
        "minimums": {
            "deposit_erg": MIN_DEPOSIT_ERG,
            "withdraw_rtc": MIN_WITHDRAW_RTC,
        },
        "required_confirmations": REQUIRED_CONFIRMATIONS,
        "platform_balance": balance,
        "explorer_url": f"https://explorer.ergoplatform.com/en/addresses/{ERGO_PLATFORM_ADDRESS}",
    })


@ergo_bp.route("/api/ergo/deposit", methods=["POST"])
def ergo_deposit():
    """Verify an ERG deposit and credit RTC.

    Request JSON:
      {
        "tx_id": "ergo_transaction_id_hex"
      }

    Auth: Session cookie or API key.
    """
    user_id = session.get("user_id")
    api_key = request.headers.get("X-API-Key", "")

    if not user_id and not api_key:
        return jsonify({"error": "Authentication required"}), 401

    db = get_db()
    if api_key:
        agent = db.execute(
            "SELECT id FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Invalid API key"}), 401
        agent_id = agent["id"]
    else:
        agent_id = user_id

    data = request.get_json() or {}
    tx_id = data.get("tx_id", "").strip()
    if not tx_id:
        return jsonify({"error": "tx_id required"}), 400

    # Check if already claimed
    existing = db.execute(
        "SELECT id FROM ergo_deposits WHERE tx_id = ?", (tx_id,)
    ).fetchone()
    if existing:
        return jsonify({"error": "Transaction already claimed"}), 409

    # Verify on-chain
    result = verify_ergo_tx(tx_id)
    if not result["ok"]:
        return jsonify({"error": result["error"]}), 400

    amount_erg = result["amount_erg"]
    confirmations = result["confirmations"]

    if amount_erg < MIN_DEPOSIT_ERG:
        return jsonify({
            "error": f"Deposit too small. Minimum is {MIN_DEPOSIT_ERG} ERG, got {amount_erg} ERG"
        }), 400

    if confirmations < REQUIRED_CONFIRMATIONS:
        return jsonify({
            "error": f"Not enough confirmations. Need {REQUIRED_CONFIRMATIONS}, got {confirmations}. Try again shortly.",
            "confirmations": confirmations,
            "required": REQUIRED_CONFIRMATIONS,
        }), 400

    # Calculate RTC credit
    fee_erg = round(amount_erg * DEPOSIT_FEE_PERCENT / 100, 9)
    net_erg = round(amount_erg - fee_erg, 9)
    rtc_amount = round(net_erg * ERG_TO_RTC_RATE, 6)

    # Record deposit
    db.execute(
        "INSERT INTO ergo_deposits (tx_id, from_address, amount_erg, fee_erg, net_erg, "
        "rtc_credited, agent_id, confirmations, status, created_at, confirmed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'credited', ?, ?)",
        (tx_id, result["from_address"], amount_erg, fee_erg, net_erg,
         rtc_amount, agent_id, confirmations, time.time(), time.time()),
    )
    db.commit()

    # Credit RTC
    _award_rtc(db, agent_id, rtc_amount, f"ergo_deposit:{tx_id[:16]}")

    return jsonify({
        "ok": True,
        "tx_id": tx_id,
        "amount_erg": amount_erg,
        "fee_erg": fee_erg,
        "net_erg": net_erg,
        "rtc_credited": rtc_amount,
        "rate": ERG_TO_RTC_RATE,
        "confirmations": confirmations,
    })


@ergo_bp.route("/api/ergo/withdraw", methods=["POST"])
def ergo_withdraw():
    """Request RTC → ERG withdrawal.

    Request JSON:
      {
        "amount_rtc": 10.0,
        "address": "9f..."  // Ergo mainnet address
      }

    Auth: Session cookie or API key.
    """
    user_id = session.get("user_id")
    api_key = request.headers.get("X-API-Key", "")

    if not user_id and not api_key:
        return jsonify({"error": "Authentication required"}), 401

    db = get_db()
    if api_key:
        agent = db.execute(
            "SELECT id FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Invalid API key"}), 401
        agent_id = agent["id"]
    else:
        agent_id = user_id

    data = request.get_json() or {}
    amount_rtc = float(data.get("amount_rtc", 0))
    to_address = data.get("address", "").strip()

    if amount_rtc < MIN_WITHDRAW_RTC:
        return jsonify({
            "error": f"Minimum withdrawal is {MIN_WITHDRAW_RTC} RTC"
        }), 400

    if not to_address or not to_address.startswith("9"):
        return jsonify({
            "error": "Valid Ergo mainnet address required (starts with 9)"
        }), 400

    # Calculate ERG amount
    total_rtc = amount_rtc + WITHDRAW_FEE_RTC
    erg_amount = round(amount_rtc / ERG_TO_RTC_RATE, 9)

    # Debit RTC
    if not _debit_rtc(db, agent_id, total_rtc):
        return jsonify({
            "error": f"Insufficient RTC balance. Need {total_rtc} RTC (including {WITHDRAW_FEE_RTC} fee)"
        }), 400

    # Record withdrawal (pending admin processing)
    db.execute(
        "INSERT INTO ergo_withdrawals (agent_id, amount_rtc, fee_rtc, net_rtc, erg_amount, "
        "to_address, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
        (agent_id, amount_rtc, WITHDRAW_FEE_RTC, amount_rtc, erg_amount,
         to_address, time.time()),
    )
    db.commit()

    return jsonify({
        "ok": True,
        "amount_rtc": amount_rtc,
        "fee_rtc": WITHDRAW_FEE_RTC,
        "erg_amount": erg_amount,
        "to_address": to_address,
        "status": "pending",
        "note": "Withdrawal will be processed by admin. ERG will be sent to your address.",
    })


@ergo_bp.route("/api/ergo/history")
def ergo_history():
    """Get ERG bridge transaction history for authenticated user."""
    user_id = session.get("user_id")
    api_key = request.headers.get("X-API-Key", "")

    if not user_id and not api_key:
        return jsonify({"error": "Authentication required"}), 401

    db = get_db()
    if api_key:
        agent = db.execute(
            "SELECT id FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Invalid API key"}), 401
        agent_id = agent["id"]
    else:
        agent_id = user_id

    limit = min(int(request.args.get("limit", 20)), 50)

    deposits = db.execute(
        "SELECT tx_id, amount_erg, fee_erg, rtc_credited, status, created_at "
        "FROM ergo_deposits WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
        (agent_id, limit),
    ).fetchall()

    withdrawals = db.execute(
        "SELECT amount_rtc, fee_rtc, erg_amount, to_address, tx_id, status, created_at "
        "FROM ergo_withdrawals WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
        (agent_id, limit),
    ).fetchall()

    return jsonify({
        "deposits": [dict(d) for d in deposits],
        "withdrawals": [dict(w) for w in withdrawals],
    })


@ergo_bp.route("/api/ergo/rate")
def ergo_rate():
    """Get current ERG ↔ RTC exchange rate."""
    return jsonify({
        "erg_to_rtc": ERG_TO_RTC_RATE,
        "rtc_to_erg": round(1.0 / ERG_TO_RTC_RATE, 6) if ERG_TO_RTC_RATE > 0 else 0,
        "erg_price_usd_approx": 0.80,
        "rtc_price_usd_approx": 0.10,
    })


@ergo_bp.route("/api/ergo/process-withdrawals", methods=["POST"])
def process_withdrawals():
    """Admin endpoint: mark withdrawals as completed with TX ID.

    Request JSON:
      {
        "withdrawal_id": 1,
        "tx_id": "ergo_tx_hash"
      }
    """
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != ADMIN_KEY:
        return jsonify({"error": "Admin key required"}), 401

    data = request.get_json() or {}
    withdrawal_id = data.get("withdrawal_id")
    tx_id = data.get("tx_id", "").strip()

    if not withdrawal_id or not tx_id:
        return jsonify({"error": "withdrawal_id and tx_id required"}), 400

    db = get_db()
    db.execute(
        "UPDATE ergo_withdrawals SET status = 'completed', tx_id = ?, completed_at = ? "
        "WHERE id = ? AND status = 'pending'",
        (tx_id, time.time(), withdrawal_id),
    )
    db.commit()

    return jsonify({"ok": True, "withdrawal_id": withdrawal_id, "tx_id": tx_id})


@ergo_bp.route("/api/ergo/pending-withdrawals")
def pending_withdrawals():
    """Admin endpoint: list pending withdrawals."""
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != ADMIN_KEY:
        return jsonify({"error": "Admin key required"}), 401

    db = get_db()
    pending = db.execute(
        "SELECT w.id, w.agent_id, a.agent_name, w.amount_rtc, w.erg_amount, "
        "w.to_address, w.created_at "
        "FROM ergo_withdrawals w JOIN agents a ON w.agent_id = a.id "
        "WHERE w.status = 'pending' ORDER BY w.created_at",
    ).fetchall()

    return jsonify({
        "pending": [dict(p) for p in pending],
        "count": len(pending),
    })
