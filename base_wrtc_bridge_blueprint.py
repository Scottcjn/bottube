"""
BoTTube wRTC Bridge — Base L2 (Ethereum)

Custodial bridge between on-chain wRTC (ERC-20 on Base) and BoTTube RTC credits.
Mirrors the Solana wRTC bridge architecture exactly:
- On-chain deposit verification via eth_getTransactionReceipt
- Authenticated withdrawal queue
- Deposit/withdraw history
- Public bridge page + stats

Deposit verification uses raw JSON-RPC (no web3 dependency).
Withdrawal processing uses web3.py for signing and sending.
"""

import json
import os
import re
import secrets
import sqlite3
import time

import requests as http_requests
from flask import Blueprint, g, jsonify, render_template, request

base_wrtc_bp = Blueprint("base_wrtc_bridge", __name__)

# ─── Base Chain Configuration ─────────────────────────────────
BASE_RPC = os.environ.get("BASE_RPC", "https://mainnet.base.org")
BASE_CHAIN_ID = 8453
WRTC_BASE_CONTRACT = os.environ.get("WRTC_BASE_CONTRACT", "")
WRTC_DECIMALS = 6
BASE_RESERVE_WALLET = os.environ.get("BASE_RESERVE_WALLET", "")
BASE_RESERVE_PRIVATE_KEY = os.environ.get("BASE_RESERVE_PRIVATE_KEY", "")

# ERC-20 Transfer(address,address,uint256) event signature
TRANSFER_EVENT_SIG = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Bridge limits (wRTC amounts)
BASE_MIN_DEPOSIT = float(os.environ.get("BASE_WRTC_MIN_DEPOSIT", "1.0"))
BASE_MIN_WITHDRAW = float(os.environ.get("BASE_WRTC_MIN_WITHDRAW", "10.0"))
BASE_MAX_WITHDRAW = float(os.environ.get("BASE_WRTC_MAX_WITHDRAW", "100000"))
BASE_WITHDRAW_FEE = float(os.environ.get("BASE_WRTC_WITHDRAW_FEE", "0.5"))
BASE_WITHDRAW_COOLDOWN = int(os.environ.get("BASE_WRTC_WITHDRAW_COOLDOWN", "3600"))

# Admin key (reuse main BoTTube admin key)
ADMIN_KEY = os.environ.get("BOTTUBE_ADMIN_KEY", "bottube_admin_key_2026")

_ETH_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ETH_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

# Minimal ABI for bridge mint/burn operations
BRIDGE_ABI = [
    {
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "burn",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def get_db():
    """Get database connection from Flask g."""
    if "db" in g:
        return g.db
    db_path = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")
    g.db = sqlite3.connect(db_path)
    g.db.row_factory = sqlite3.Row
    return g.db


def init_base_wrtc_tables(db):
    """Create Base bridge tables if they don't exist."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS base_wrtc_deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_hash TEXT UNIQUE NOT NULL,
            from_address TEXT NOT NULL,
            amount_wrtc REAL NOT NULL,
            agent_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL DEFAULT '',
            block_number INTEGER,
            status TEXT DEFAULT 'credited',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_base_wrtc_deposits_agent
            ON base_wrtc_deposits(agent_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS base_wrtc_withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            withdrawal_id TEXT UNIQUE NOT NULL,
            agent_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL DEFAULT '',
            to_address TEXT NOT NULL,
            amount_wrtc REAL NOT NULL,
            fee_wrtc REAL DEFAULT 0.5,
            net_wrtc REAL NOT NULL,
            tx_hash TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at REAL NOT NULL,
            completed_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_base_wrtc_withdrawals_agent
            ON base_wrtc_withdrawals(agent_id, created_at DESC);
        """
    )
    db.commit()


# ─── On-Chain Verification ────────────────────────────────────

def verify_base_wrtc_transfer(tx_hash):
    """Verify a wRTC ERC-20 transfer on Base chain via JSON-RPC.

    Parses the transaction receipt for Transfer events from the
    wRTC contract. Returns (transfer_dict, None) on success
    or (None, error_string) on failure.
    """
    if not tx_hash or not _ETH_TX_RE.match(tx_hash):
        return None, "Invalid transaction hash format (need 0x + 64 hex chars)"

    if not WRTC_BASE_CONTRACT:
        return None, "WRTC_BASE_CONTRACT not configured"

    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getTransactionReceipt",
            "params": [tx_hash],
            "id": 1,
        }
        resp = http_requests.post(BASE_RPC, json=payload, timeout=15)
        if not resp.ok:
            return None, f"RPC request failed: HTTP {resp.status_code}"

        result = resp.json().get("result")
        if not result:
            return None, "Transaction not found or not yet confirmed"

        # Check status (0x1 = success)
        if result.get("status") != "0x1":
            return None, "Transaction reverted on-chain"

        # Check confirmation depth (Base L2 finalizes fast, but require 12 blocks)
        tx_block = int(result.get("blockNumber", "0x0"), 16)
        head_payload = {
            "jsonrpc": "2.0",
            "method": "eth_blockNumber",
            "params": [],
            "id": 2,
        }
        head_resp = http_requests.post(BASE_RPC, json=head_payload, timeout=10)
        if head_resp.ok:
            head_block = int(head_resp.json().get("result", "0x0"), 16)
            confirmations = head_block - tx_block
            if confirmations < 12:
                return None, f"Transaction needs more confirmations ({confirmations}/12). Try again shortly."

        # Parse logs for wRTC Transfer events
        for log in result.get("logs", []):
            topics = log.get("topics", [])
            if (
                log.get("address", "").lower() == WRTC_BASE_CONTRACT.lower()
                and len(topics) >= 3
                and topics[0].lower() == TRANSFER_EVENT_SIG.lower()
            ):
                from_addr = "0x" + topics[1][-40:]
                to_addr = "0x" + topics[2][-40:]
                amount_raw = int(log.get("data", "0x0"), 16)
                amount_wrtc = amount_raw / (10 ** WRTC_DECIMALS)
                block_number = int(result.get("blockNumber", "0x0"), 16)

                return {
                    "tx_hash": tx_hash,
                    "from_address": from_addr.lower(),
                    "to_address": to_addr.lower(),
                    "amount_raw": str(amount_raw),
                    "amount_wrtc": amount_wrtc,
                    "block_number": block_number,
                    "chain": "base",
                }, None

        return None, "No wRTC Transfer event found in transaction logs"

    except Exception as exc:
        return None, f"Verification error: {exc}"


# ─── Authentication Helper ────────────────────────────────────

def _get_authenticated_agent():
    """Get agent row from API key header."""
    api_key = (request.headers.get("X-API-Key") or "").strip()
    if not api_key:
        return None
    db = get_db()
    return db.execute(
        "SELECT id, agent_name, eth_address, rtc_balance FROM agents WHERE api_key = ?",
        (api_key,),
    ).fetchone()


# ─── Endpoints ────────────────────────────────────────────────

@base_wrtc_bp.route("/api/base-bridge/info", methods=["GET"])
def base_bridge_info():
    """Public bridge info — contract, fees, limits, stats."""
    db = get_db()
    init_base_wrtc_tables(db)

    dep = db.execute(
        """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(amount_wrtc), 0) AS total
        FROM base_wrtc_deposits WHERE status = 'credited'
        """
    ).fetchone()
    wd = db.execute(
        """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(amount_wrtc), 0) AS total
        FROM base_wrtc_withdrawals WHERE status IN ('pending', 'processing', 'sent', 'completed')
        """
    ).fetchone()

    return jsonify(
        {
            "network": "base",
            "chain_id": BASE_CHAIN_ID,
            "contract": WRTC_BASE_CONTRACT,
            "decimals": WRTC_DECIMALS,
            "reserve_wallet": BASE_RESERVE_WALLET,
            "basescan_url": f"https://basescan.org/token/{WRTC_BASE_CONTRACT}"
            if WRTC_BASE_CONTRACT
            else "",
            "swap_url": f"https://app.uniswap.org/swap?chain=base&outputCurrency={WRTC_BASE_CONTRACT}"
            if WRTC_BASE_CONTRACT
            else "",
            "limits": {
                "min_deposit_wrtc": BASE_MIN_DEPOSIT,
                "min_withdraw_wrtc": BASE_MIN_WITHDRAW,
                "max_withdraw_wrtc": BASE_MAX_WITHDRAW,
                "withdraw_cooldown_s": BASE_WITHDRAW_COOLDOWN,
            },
            "fees": {
                "deposit_wrtc": 0.0,
                "withdraw_wrtc": BASE_WITHDRAW_FEE,
            },
            "stats": {
                "deposits_count": dep["cnt"],
                "total_deposited_wrtc": dep["total"],
                "withdrawals_count": wd["cnt"],
                "total_withdrawn_wrtc": wd["total"],
            },
        }
    )


@base_wrtc_bp.route("/api/base-bridge/deposit", methods=["POST"])
def base_bridge_deposit():
    """Verify a Base chain TX and credit RTC balance."""
    agent = _get_authenticated_agent()
    if not agent:
        return jsonify({"error": "Authentication required. Provide X-API-Key header."}), 401

    data = request.get_json(silent=True) or {}
    tx_hash = (data.get("tx_hash") or "").strip().lower()
    if not _ETH_TX_RE.match(tx_hash):
        return jsonify({"error": "tx_hash required (0x-prefixed, 66 chars)"}), 400

    db = get_db()
    init_base_wrtc_tables(db)

    # Idempotency check
    existing = db.execute(
        "SELECT * FROM base_wrtc_deposits WHERE tx_hash = ?", (tx_hash,)
    ).fetchone()
    if existing:
        if existing["agent_id"] != agent["id"]:
            return jsonify({"error": "Transaction already claimed by another account"}), 409
        return jsonify({"ok": True, "idempotent": True, "deposit": dict(existing)})

    # Verify on-chain
    transfer, err = verify_base_wrtc_transfer(tx_hash)
    if not transfer:
        return jsonify({"error": f"Verification failed: {err}"}), 400

    # Check transfer was sent to our reserve wallet
    if transfer["to_address"].lower() != BASE_RESERVE_WALLET.lower():
        return jsonify(
            {
                "error": "Transfer was not sent to the bridge reserve wallet",
                "expected": BASE_RESERVE_WALLET,
                "got": transfer["to_address"],
            }
        ), 400

    # Anti-theft: sender must match account's bound Ethereum address
    account_eth = (agent["eth_address"] or "").strip().lower()
    if not account_eth:
        return jsonify(
            {
                "error": (
                    "No Ethereum wallet bound to your account. "
                    "Set your ETH address in profile settings before deposit verification."
                )
            }
        ), 400
    if account_eth != transfer["from_address"].lower():
        return jsonify(
            {
                "error": "Sender wallet does not match your account's verified ETH address",
                "expected_sender": account_eth,
                "onchain_sender": transfer["from_address"],
            }
        ), 403

    # Minimum deposit check
    if transfer["amount_wrtc"] < BASE_MIN_DEPOSIT:
        return jsonify(
            {"error": f"Minimum deposit is {BASE_MIN_DEPOSIT} wRTC", "received": transfer["amount_wrtc"]}
        ), 400

    # Record deposit and credit balance
    db.execute(
        """
        INSERT INTO base_wrtc_deposits (
            tx_hash, from_address, amount_wrtc, agent_id, agent_name,
            block_number, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'credited', ?)
        """,
        (
            transfer["tx_hash"],
            transfer["from_address"],
            transfer["amount_wrtc"],
            agent["id"],
            agent["agent_name"],
            transfer["block_number"],
            time.time(),
        ),
    )
    db.execute(
        "UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?",
        (transfer["amount_wrtc"], agent["id"]),
    )
    db.commit()

    new_balance = db.execute(
        "SELECT rtc_balance FROM agents WHERE id = ?", (agent["id"],)
    ).fetchone()
    return jsonify(
        {
            "ok": True,
            "chain": "base",
            "deposit": transfer,
            "credited_rtc": transfer["amount_wrtc"],
            "new_rtc_balance": new_balance["rtc_balance"],
        }
    )


@base_wrtc_bp.route("/api/base-bridge/withdraw", methods=["POST"])
def base_bridge_withdraw():
    """Queue a withdrawal from RTC credits to on-chain wRTC on Base."""
    agent = _get_authenticated_agent()
    if not agent:
        return jsonify({"error": "Authentication required. Provide X-API-Key header."}), 401

    data = request.get_json(silent=True) or {}
    to_address = (data.get("to_address") or "").strip()
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0.0

    if not _ETH_ADDR_RE.match(to_address):
        return jsonify({"error": "Valid Base/Ethereum destination address required (0x + 40 hex)"}), 400
    if amount < BASE_MIN_WITHDRAW:
        return jsonify({"error": f"Minimum withdrawal is {BASE_MIN_WITHDRAW} wRTC"}), 400
    if amount > BASE_MAX_WITHDRAW:
        return jsonify({"error": f"Maximum withdrawal is {BASE_MAX_WITHDRAW} wRTC"}), 400

    db = get_db()
    init_base_wrtc_tables(db)

    # Cooldown check
    last_wd = db.execute(
        """
        SELECT created_at FROM base_wrtc_withdrawals
        WHERE agent_id = ? ORDER BY created_at DESC LIMIT 1
        """,
        (agent["id"],),
    ).fetchone()
    if last_wd and (time.time() - last_wd["created_at"]) < BASE_WITHDRAW_COOLDOWN:
        remaining = int(BASE_WITHDRAW_COOLDOWN - (time.time() - last_wd["created_at"]))
        return jsonify(
            {"error": f"Withdrawal cooldown active. Try again in {remaining}s."}
        ), 429

    # Balance check
    total_debit = round(amount + BASE_WITHDRAW_FEE, WRTC_DECIMALS)
    balance = float(agent["rtc_balance"] or 0.0)
    if balance < total_debit:
        return jsonify(
            {
                "error": "Insufficient RTC balance",
                "balance": balance,
                "required": total_debit,
                "amount": amount,
                "fee": BASE_WITHDRAW_FEE,
            }
        ), 400

    now = time.time()
    net = round(amount, WRTC_DECIMALS)
    withdrawal_id = f"bwd_{int(now)}_{secrets.token_hex(4)}"
    db.execute(
        """
        INSERT INTO base_wrtc_withdrawals (
            withdrawal_id, agent_id, agent_name, to_address,
            amount_wrtc, fee_wrtc, net_wrtc, tx_hash,
            status, created_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, '', 'pending', ?, NULL)
        """,
        (
            withdrawal_id,
            agent["id"],
            agent["agent_name"],
            to_address,
            amount,
            BASE_WITHDRAW_FEE,
            net,
            now,
        ),
    )
    db.execute(
        "UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?",
        (total_debit, agent["id"]),
    )
    db.commit()

    new_balance = db.execute(
        "SELECT rtc_balance FROM agents WHERE id = ?", (agent["id"],)
    ).fetchone()
    return jsonify(
        {
            "ok": True,
            "chain": "base",
            "withdrawal": {
                "withdrawal_id": withdrawal_id,
                "to_address": to_address,
                "amount_wrtc": amount,
                "fee_wrtc": BASE_WITHDRAW_FEE,
                "net_wrtc": net,
                "status": "pending",
            },
            "new_rtc_balance": new_balance["rtc_balance"],
        }
    )


@base_wrtc_bp.route("/api/base-bridge/history", methods=["GET"])
def base_bridge_history():
    """Deposit and withdrawal history for the authenticated agent."""
    agent = _get_authenticated_agent()
    if not agent:
        return jsonify({"error": "Authentication required. Provide X-API-Key header."}), 401

    limit = min(200, max(1, request.args.get("limit", 50, type=int)))
    db = get_db()
    init_base_wrtc_tables(db)

    deposits = db.execute(
        """
        SELECT tx_hash AS reference_id, amount_wrtc, from_address,
               block_number, created_at, 'deposit' AS type, status
        FROM base_wrtc_deposits
        WHERE agent_id = ?
        ORDER BY created_at DESC LIMIT ?
        """,
        (agent["id"], limit),
    ).fetchall()
    withdrawals = db.execute(
        """
        SELECT withdrawal_id AS reference_id, amount_wrtc, to_address AS from_address,
               0 AS block_number, created_at, 'withdraw' AS type, status
        FROM base_wrtc_withdrawals
        WHERE agent_id = ?
        ORDER BY created_at DESC LIMIT ?
        """,
        (agent["id"], limit),
    ).fetchall()

    combined = [dict(r) for r in deposits] + [dict(r) for r in withdrawals]
    combined.sort(key=lambda r: r.get("created_at", 0), reverse=True)

    return jsonify({"ok": True, "chain": "base", "history": combined[:limit]})


@base_wrtc_bp.route("/api/base-bridge/process-withdrawals", methods=["POST"])
def base_bridge_process_withdrawals():
    """Admin endpoint: process pending withdrawals via web3.py.

    Sends wRTC tokens from the reserve wallet to each queued address.
    Requires BOTTUBE_ADMIN_KEY header and BASE_RESERVE_PRIVATE_KEY env.
    """
    admin_key = (request.headers.get("X-Admin-Key") or "").strip()
    if admin_key != ADMIN_KEY:
        return jsonify({"error": "Admin authentication required"}), 401

    if not BASE_RESERVE_PRIVATE_KEY:
        return jsonify({"error": "BASE_RESERVE_PRIVATE_KEY not configured on server"}), 500
    if not WRTC_BASE_CONTRACT:
        return jsonify({"error": "WRTC_BASE_CONTRACT not configured on server"}), 500

    try:
        from web3 import Web3
    except ImportError:
        return jsonify({"error": "web3 package not installed (pip install web3)"}), 500

    db = get_db()
    init_base_wrtc_tables(db)

    pending = db.execute(
        "SELECT * FROM base_wrtc_withdrawals WHERE status = 'pending' ORDER BY created_at ASC LIMIT 20"
    ).fetchall()

    if not pending:
        return jsonify({"ok": True, "processed": 0, "message": "No pending withdrawals"})

    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    if not w3.is_connected():
        return jsonify({"error": "Cannot connect to Base RPC"}), 502

    account = w3.eth.account.from_key(BASE_RESERVE_PRIVATE_KEY)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(WRTC_BASE_CONTRACT), abi=BRIDGE_ABI
    )

    results = []
    for wd in pending:
        wd = dict(wd)
        try:
            db.execute(
                "UPDATE base_wrtc_withdrawals SET status = 'processing' WHERE id = ?",
                (wd["id"],),
            )
            db.commit()

            amount_raw = int(wd["net_wrtc"] * (10 ** WRTC_DECIMALS))
            to_addr = Web3.to_checksum_address(wd["to_address"])

            nonce = w3.eth.get_transaction_count(account.address)
            tx = contract.functions.mint(to_addr, amount_raw).build_transaction(
                {
                    "chainId": BASE_CHAIN_ID,
                    "from": account.address,
                    "nonce": nonce,
                    "maxFeePerGas": w3.eth.gas_price * 2,
                    "maxPriorityFeePerGas": w3.to_wei(0.001, "gwei"),
                }
            )
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt.status == 1:
                db.execute(
                    """
                    UPDATE base_wrtc_withdrawals
                    SET status = 'completed', tx_hash = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (receipt.transactionHash.hex(), time.time(), wd["id"]),
                )
                results.append(
                    {
                        "withdrawal_id": wd["withdrawal_id"],
                        "status": "completed",
                        "tx_hash": receipt.transactionHash.hex(),
                    }
                )
            else:
                db.execute(
                    "UPDATE base_wrtc_withdrawals SET status = 'failed' WHERE id = ?",
                    (wd["id"],),
                )
                results.append(
                    {"withdrawal_id": wd["withdrawal_id"], "status": "failed", "reason": "tx reverted"}
                )

        except Exception as exc:
            db.execute(
                "UPDATE base_wrtc_withdrawals SET status = 'failed' WHERE id = ?",
                (wd["id"],),
            )
            results.append(
                {"withdrawal_id": wd["withdrawal_id"], "status": "failed", "reason": str(exc)}
            )

        db.commit()

    return jsonify(
        {
            "ok": True,
            "processed": len(results),
            "results": results,
        }
    )


@base_wrtc_bp.route("/api/base-bridge/stats", methods=["GET"])
def base_bridge_stats():
    """Public aggregate bridge statistics."""
    db = get_db()
    init_base_wrtc_tables(db)

    dep = db.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(amount_wrtc), 0) AS total FROM base_wrtc_deposits"
    ).fetchone()
    wd = db.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(amount_wrtc), 0) AS total FROM base_wrtc_withdrawals"
    ).fetchone()
    completed = db.execute(
        "SELECT COUNT(*) AS cnt FROM base_wrtc_withdrawals WHERE status = 'completed'"
    ).fetchone()
    pending_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM base_wrtc_withdrawals WHERE status = 'pending'"
    ).fetchone()

    return jsonify(
        {
            "chain": "base",
            "chain_id": BASE_CHAIN_ID,
            "contract": WRTC_BASE_CONTRACT,
            "total_deposits": dep["cnt"],
            "total_deposited_wrtc": dep["total"],
            "total_withdrawals": wd["cnt"],
            "total_withdrawn_wrtc": wd["total"],
            "completed_withdrawals": completed["cnt"],
            "pending_withdrawals": pending_count["cnt"],
        }
    )


# ─── Bridge Pages ─────────────────────────────────────────────

@base_wrtc_bp.route("/bridge/base")
def base_bridge_page():
    """Base chain bridge console UI."""
    return render_template(
        "bridge_base.html",
        wrtc_contract=WRTC_BASE_CONTRACT,
        reserve_wallet=BASE_RESERVE_WALLET,
        wrtc_decimals=WRTC_DECIMALS,
        chain_id=BASE_CHAIN_ID,
        basescan_url=f"https://basescan.org/token/{WRTC_BASE_CONTRACT}" if WRTC_BASE_CONTRACT else "",
        swap_url=f"https://app.uniswap.org/swap?chain=base&outputCurrency={WRTC_BASE_CONTRACT}"
        if WRTC_BASE_CONTRACT
        else "",
    )
