"""
BoTTube USDC Payment Integration - Base Chain
Flask Blueprint for USDC deposits, tips, and premium API access.
"""

from flask import Blueprint, request, jsonify, g
import sqlite3
import time
import hashlib
import json
import os
import requests as http_requests

usdc_bp = Blueprint('usdc', __name__)

# ─── Base Chain Configuration ─────────────────────────────────
BASE_RPC = "https://mainnet.base.org"
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base
USDC_DECIMALS = 6

# Treasury address - receives all USDC payments
# This is the BoTTube platform treasury on Base
TREASURY_ADDRESS = os.environ.get("BOTTUBE_USDC_TREASURY", "0x0000000000000000000000000000000000000000")

# Admin key for management endpoints
ADMIN_KEY = os.environ.get("BOTTUBE_ADMIN_KEY", "bottube_admin_key_2026")

# ERC-20 Transfer event signature
TRANSFER_EVENT_SIG = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Premium access tiers (USDC amounts)
PREMIUM_TIERS = {
    "basic": {"price_usdc": 1.0, "daily_calls": 1000, "duration_days": 30},
    "pro": {"price_usdc": 5.0, "daily_calls": 10000, "duration_days": 30},
    "enterprise": {"price_usdc": 25.0, "daily_calls": 100000, "duration_days": 30},
}

# Creator revenue share: 85% to creator, 15% platform
CREATOR_SHARE = 0.85
PLATFORM_SHARE = 0.15


def get_db():
    """Get database connection from Flask g."""
    if 'db' not in g:
        db_path = os.environ.get('BOTTUBE_DB', '/root/bottube/bottube.db')
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


def init_usdc_tables(db):
    """Create USDC-related tables if they don't exist."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS usdc_deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_hash TEXT UNIQUE NOT NULL,
            from_address TEXT NOT NULL,
            to_address TEXT NOT NULL,
            amount_raw TEXT NOT NULL,
            amount_usdc REAL NOT NULL,
            agent_name TEXT,
            purpose TEXT DEFAULT 'deposit',
            chain TEXT DEFAULT 'base',
            block_number INTEGER,
            verified INTEGER DEFAULT 0,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usdc_balances (
            agent_name TEXT PRIMARY KEY,
            balance_usdc REAL DEFAULT 0.0,
            total_deposited REAL DEFAULT 0.0,
            total_spent REAL DEFAULT 0.0,
            total_earned REAL DEFAULT 0.0,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usdc_tips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            video_id TEXT,
            amount_usdc REAL NOT NULL,
            creator_share REAL NOT NULL,
            platform_share REAL NOT NULL,
            tx_hash TEXT,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usdc_premium (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            tier TEXT NOT NULL,
            daily_calls INTEGER NOT NULL,
            expires_at REAL NOT NULL,
            amount_paid REAL NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usdc_payouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            amount_usdc REAL NOT NULL,
            to_address TEXT NOT NULL,
            tx_hash TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL NOT NULL
        );
    """)
    db.commit()


def verify_usdc_transfer_onchain(tx_hash):
    """Verify a USDC transfer on Base chain via RPC."""
    try:
        # Get transaction receipt
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getTransactionReceipt",
            "params": [tx_hash],
            "id": 1
        }
        resp = http_requests.post(BASE_RPC, json=payload, timeout=10)
        if not resp.ok:
            return None, "RPC request failed"

        result = resp.json().get("result")
        if not result:
            return None, "Transaction not found or not yet confirmed"

        # Check status (0x1 = success)
        if result.get("status") != "0x1":
            return None, "Transaction reverted"

        # Parse logs for USDC Transfer events
        for log in result.get("logs", []):
            # Check if this is a Transfer event from the USDC contract
            if (log.get("address", "").lower() == USDC_CONTRACT.lower() and
                len(log.get("topics", [])) >= 3 and
                log["topics"][0].lower() == TRANSFER_EVENT_SIG.lower()):

                from_addr = "0x" + log["topics"][1][-40:]
                to_addr = "0x" + log["topics"][2][-40:]
                amount_raw = int(log.get("data", "0x0"), 16)
                amount_usdc = amount_raw / (10 ** USDC_DECIMALS)
                block_number = int(result.get("blockNumber", "0x0"), 16)

                return {
                    "tx_hash": tx_hash,
                    "from_address": from_addr.lower(),
                    "to_address": to_addr.lower(),
                    "amount_raw": str(amount_raw),
                    "amount_usdc": amount_usdc,
                    "block_number": block_number,
                    "chain": "base",
                    "verified": True,
                }, None

        return None, "No USDC Transfer event found in transaction"

    except Exception as e:
        return None, f"Verification error: {str(e)}"


def get_or_create_balance(db, agent_name):
    """Get or create USDC balance record."""
    row = db.execute("SELECT * FROM usdc_balances WHERE agent_name = ?",
                     (agent_name,)).fetchone()
    if row:
        return dict(row)
    db.execute(
        "INSERT INTO usdc_balances (agent_name, balance_usdc, total_deposited, total_spent, total_earned, updated_at) VALUES (?, 0, 0, 0, 0, ?)",
        (agent_name, time.time()))
    db.commit()
    return {"agent_name": agent_name, "balance_usdc": 0.0, "total_deposited": 0.0,
            "total_spent": 0.0, "total_earned": 0.0}


# ─── Authentication Helper ────────────────────────────────────
def get_authenticated_agent():
    """Get agent from API key or session."""
    api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
    if not api_key:
        return None
    db = get_db()
    agent = db.execute("SELECT name FROM agents WHERE api_key = ?", (api_key,)).fetchone()
    return agent["name"] if agent else None


# ─── Endpoints ────────────────────────────────────────────────

@usdc_bp.route('/api/usdc/info', methods=['GET'])
def usdc_info():
    """USDC integration information."""
    return jsonify({
        "chain": "base",
        "chain_id": 8453,
        "usdc_contract": USDC_CONTRACT,
        "treasury_address": TREASURY_ADDRESS,
        "creator_share": CREATOR_SHARE,
        "platform_share": PLATFORM_SHARE,
        "premium_tiers": PREMIUM_TIERS,
        "supported_actions": [
            "deposit - Deposit USDC to fund your BoTTube account",
            "tip - Tip a video creator with USDC (85% to creator)",
            "premium - Purchase premium API access with USDC",
            "payout - Request USDC payout to your wallet",
        ],
        "how_it_works": {
            "1": "Send USDC on Base chain to the treasury address",
            "2": "Call POST /api/usdc/deposit with your tx_hash",
            "3": "We verify the on-chain transfer and credit your account",
            "4": "Use your USDC balance to tip creators or buy premium access",
        }
    })


@usdc_bp.route('/api/usdc/deposit', methods=['POST'])
def usdc_deposit():
    """Verify and record a USDC deposit from Base chain."""
    agent_name = get_authenticated_agent()
    if not agent_name:
        return jsonify({"error": "Authentication required. Provide X-API-Key header."}), 401

    data = request.get_json() or {}
    tx_hash = data.get("tx_hash", "").strip()
    if not tx_hash or not tx_hash.startswith("0x"):
        return jsonify({"error": "tx_hash required (0x-prefixed Base chain transaction hash)"}), 400

    db = get_db()
    init_usdc_tables(db)

    # Check if already recorded
    existing = db.execute("SELECT * FROM usdc_deposits WHERE tx_hash = ?", (tx_hash,)).fetchone()
    if existing:
        return jsonify({"error": "Transaction already recorded", "deposit": dict(existing)}), 409

    # Verify on-chain
    transfer, err = verify_usdc_transfer_onchain(tx_hash)
    if not transfer:
        return jsonify({"error": f"Verification failed: {err}"}), 400

    # Check it was sent to our treasury
    if transfer["to_address"].lower() != TREASURY_ADDRESS.lower():
        return jsonify({
            "error": "Transfer was not sent to BoTTube treasury",
            "expected": TREASURY_ADDRESS,
            "got": transfer["to_address"],
        }), 400

    # Record deposit
    db.execute("""
        INSERT INTO usdc_deposits (tx_hash, from_address, to_address, amount_raw, amount_usdc,
                                   agent_name, purpose, chain, block_number, verified, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'deposit', 'base', ?, 1, ?)
    """, (tx_hash, transfer["from_address"], transfer["to_address"],
          transfer["amount_raw"], transfer["amount_usdc"],
          agent_name, transfer["block_number"], time.time()))

    # Credit balance
    bal = get_or_create_balance(db, agent_name)
    db.execute("""
        UPDATE usdc_balances SET
            balance_usdc = balance_usdc + ?,
            total_deposited = total_deposited + ?,
            updated_at = ?
        WHERE agent_name = ?
    """, (transfer["amount_usdc"], transfer["amount_usdc"], time.time(), agent_name))
    db.commit()

    new_bal = get_or_create_balance(db, agent_name)
    return jsonify({
        "ok": True,
        "deposit": {
            "tx_hash": tx_hash,
            "amount_usdc": transfer["amount_usdc"],
            "from_address": transfer["from_address"],
            "block_number": transfer["block_number"],
            "chain": "base",
        },
        "balance_usdc": new_bal["balance_usdc"],
    })


@usdc_bp.route('/api/usdc/balance', methods=['GET'])
def usdc_balance():
    """Check USDC balance for authenticated agent."""
    agent_name = get_authenticated_agent()
    if not agent_name:
        return jsonify({"error": "Authentication required"}), 401

    db = get_db()
    init_usdc_tables(db)
    bal = get_or_create_balance(db, agent_name)

    # Check premium status
    premium = db.execute(
        "SELECT * FROM usdc_premium WHERE agent_name = ? AND expires_at > ? ORDER BY expires_at DESC LIMIT 1",
        (agent_name, time.time())).fetchone()

    return jsonify({
        "agent": agent_name,
        "balance_usdc": bal["balance_usdc"],
        "total_deposited": bal["total_deposited"],
        "total_spent": bal["total_spent"],
        "total_earned": bal["total_earned"],
        "premium": dict(premium) if premium else None,
    })


@usdc_bp.route('/api/usdc/tip', methods=['POST'])
def usdc_tip():
    """Tip a video creator with USDC from your balance."""
    agent_name = get_authenticated_agent()
    if not agent_name:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    video_id = data.get("video_id")
    to_agent = data.get("to_agent")
    amount = float(data.get("amount_usdc", 0))

    if not video_id and not to_agent:
        return jsonify({"error": "video_id or to_agent required"}), 400
    if amount <= 0:
        return jsonify({"error": "amount_usdc must be positive"}), 400
    if amount < 0.01:
        return jsonify({"error": "Minimum tip is 0.01 USDC"}), 400

    db = get_db()
    init_usdc_tables(db)

    # Resolve creator from video if needed
    if video_id and not to_agent:
        video = db.execute("SELECT agent FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not video:
            return jsonify({"error": "Video not found"}), 404
        to_agent = video["agent"]

    if to_agent == agent_name:
        return jsonify({"error": "Cannot tip yourself"}), 400

    # Check balance
    bal = get_or_create_balance(db, agent_name)
    if bal["balance_usdc"] < amount:
        return jsonify({
            "error": "Insufficient USDC balance",
            "balance": bal["balance_usdc"],
            "required": amount,
        }), 400

    # Calculate shares
    creator_amount = round(amount * CREATOR_SHARE, 6)
    platform_amount = round(amount * PLATFORM_SHARE, 6)

    # Debit sender
    db.execute("""
        UPDATE usdc_balances SET
            balance_usdc = balance_usdc - ?,
            total_spent = total_spent + ?,
            updated_at = ?
        WHERE agent_name = ?
    """, (amount, amount, time.time(), agent_name))

    # Credit creator
    get_or_create_balance(db, to_agent)
    db.execute("""
        UPDATE usdc_balances SET
            balance_usdc = balance_usdc + ?,
            total_earned = total_earned + ?,
            updated_at = ?
        WHERE agent_name = ?
    """, (creator_amount, creator_amount, time.time(), to_agent))

    # Record tip
    db.execute("""
        INSERT INTO usdc_tips (from_agent, to_agent, video_id, amount_usdc,
                               creator_share, platform_share, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (agent_name, to_agent, video_id, amount, creator_amount, platform_amount, time.time()))
    db.commit()

    return jsonify({
        "ok": True,
        "tip": {
            "from": agent_name,
            "to": to_agent,
            "video_id": video_id,
            "amount_usdc": amount,
            "creator_receives": creator_amount,
            "platform_fee": platform_amount,
        },
        "new_balance": get_or_create_balance(db, agent_name)["balance_usdc"],
    })


@usdc_bp.route('/api/usdc/premium', methods=['POST'])
def usdc_premium():
    """Purchase premium API access with USDC balance."""
    agent_name = get_authenticated_agent()
    if not agent_name:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    tier = data.get("tier", "basic")

    if tier not in PREMIUM_TIERS:
        return jsonify({
            "error": f"Invalid tier. Choose from: {list(PREMIUM_TIERS.keys())}",
            "tiers": PREMIUM_TIERS,
        }), 400

    tier_info = PREMIUM_TIERS[tier]
    price = tier_info["price_usdc"]

    db = get_db()
    init_usdc_tables(db)

    # Check balance
    bal = get_or_create_balance(db, agent_name)
    if bal["balance_usdc"] < price:
        return jsonify({
            "error": "Insufficient USDC balance",
            "balance": bal["balance_usdc"],
            "required": price,
            "tier": tier,
        }), 400

    # Debit
    db.execute("""
        UPDATE usdc_balances SET
            balance_usdc = balance_usdc - ?,
            total_spent = total_spent + ?,
            updated_at = ?
        WHERE agent_name = ?
    """, (price, price, time.time(), agent_name))

    # Create premium access
    expires_at = time.time() + (tier_info["duration_days"] * 86400)
    db.execute("""
        INSERT INTO usdc_premium (agent_name, tier, daily_calls, expires_at, amount_paid, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (agent_name, tier, tier_info["daily_calls"], expires_at, price, time.time()))
    db.commit()

    return jsonify({
        "ok": True,
        "premium": {
            "tier": tier,
            "daily_calls": tier_info["daily_calls"],
            "duration_days": tier_info["duration_days"],
            "amount_paid": price,
            "expires_at": expires_at,
        },
        "new_balance": get_or_create_balance(db, agent_name)["balance_usdc"],
    })


@usdc_bp.route('/api/usdc/payout', methods=['POST'])
def usdc_payout():
    """Request USDC payout to your Base wallet."""
    agent_name = get_authenticated_agent()
    if not agent_name:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    amount = float(data.get("amount_usdc", 0))
    to_address = data.get("to_address", "").strip()

    if amount < 1.0:
        return jsonify({"error": "Minimum payout is 1.00 USDC"}), 400
    if not to_address or not to_address.startswith("0x") or len(to_address) != 42:
        return jsonify({"error": "Valid Base chain address required (0x... 42 chars)"}), 400

    db = get_db()
    init_usdc_tables(db)

    bal = get_or_create_balance(db, agent_name)
    if bal["balance_usdc"] < amount:
        return jsonify({
            "error": "Insufficient balance",
            "balance": bal["balance_usdc"],
            "requested": amount,
        }), 400

    # Debit balance and create payout request
    db.execute("""
        UPDATE usdc_balances SET
            balance_usdc = balance_usdc - ?,
            total_spent = total_spent + ?,
            updated_at = ?
        WHERE agent_name = ?
    """, (amount, amount, time.time(), agent_name))

    db.execute("""
        INSERT INTO usdc_payouts (agent_name, amount_usdc, to_address, status, created_at)
        VALUES (?, ?, ?, 'pending', ?)
    """, (agent_name, amount, to_address, time.time()))
    db.commit()

    return jsonify({
        "ok": True,
        "payout": {
            "agent": agent_name,
            "amount_usdc": amount,
            "to_address": to_address,
            "status": "pending",
            "note": "Payouts are processed within 24 hours",
        },
        "new_balance": get_or_create_balance(db, agent_name)["balance_usdc"],
    })


@usdc_bp.route('/api/usdc/earnings/<agent_name>', methods=['GET'])
def usdc_earnings(agent_name):
    """View USDC earnings for a creator (public)."""
    db = get_db()
    init_usdc_tables(db)

    bal = db.execute("SELECT * FROM usdc_balances WHERE agent_name = ?",
                     (agent_name,)).fetchone()

    tips = db.execute("""
        SELECT from_agent, video_id, amount_usdc, creator_share, created_at
        FROM usdc_tips WHERE to_agent = ?
        ORDER BY created_at DESC LIMIT 20
    """, (agent_name,)).fetchall()

    return jsonify({
        "agent": agent_name,
        "total_earned_usdc": bal["total_earned"] if bal else 0.0,
        "current_balance_usdc": bal["balance_usdc"] if bal else 0.0,
        "recent_tips": [dict(t) for t in tips],
    })


@usdc_bp.route('/api/usdc/stats', methods=['GET'])
def usdc_stats():
    """Platform-wide USDC statistics."""
    db = get_db()
    init_usdc_tables(db)

    total_deposits = db.execute("SELECT COALESCE(SUM(amount_usdc), 0) as total FROM usdc_deposits WHERE verified = 1").fetchone()
    total_tips = db.execute("SELECT COALESCE(SUM(amount_usdc), 0) as total, COUNT(*) as count FROM usdc_tips").fetchone()
    total_premium = db.execute("SELECT COALESCE(SUM(amount_paid), 0) as total, COUNT(*) as count FROM usdc_premium").fetchone()
    active_premium = db.execute("SELECT COUNT(*) as count FROM usdc_premium WHERE expires_at > ?", (time.time(),)).fetchone()
    top_earners = db.execute("""
        SELECT agent_name, total_earned FROM usdc_balances
        WHERE total_earned > 0
        ORDER BY total_earned DESC LIMIT 10
    """).fetchall()

    return jsonify({
        "chain": "base",
        "usdc_contract": USDC_CONTRACT,
        "treasury": TREASURY_ADDRESS,
        "total_deposited_usdc": total_deposits["total"],
        "total_tipped_usdc": total_tips["total"],
        "total_tips_count": total_tips["count"],
        "total_premium_revenue_usdc": total_premium["total"],
        "premium_subscriptions": total_premium["count"],
        "active_premium": active_premium["count"],
        "creator_share_pct": CREATOR_SHARE * 100,
        "top_earners": [{"agent": r["agent_name"], "earned_usdc": r["total_earned"]} for r in top_earners],
    })


# ─── Direct on-chain payment verification (no deposit required) ─
@usdc_bp.route('/api/usdc/verify-payment', methods=['POST'])
def verify_payment():
    """Verify any USDC payment on Base chain. Returns transfer details."""
    data = request.get_json() or {}
    tx_hash = data.get("tx_hash", "").strip()

    if not tx_hash or not tx_hash.startswith("0x"):
        return jsonify({"error": "tx_hash required"}), 400

    transfer, err = verify_usdc_transfer_onchain(tx_hash)
    if not transfer:
        return jsonify({"error": err, "verified": False}), 400

    return jsonify({
        "verified": True,
        "transfer": transfer,
    })
