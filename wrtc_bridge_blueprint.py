"""
BoTTube wRTC bridge blueprint.

Implements a custodial wRTC <-> BoTTube RTC credits bridge with:
- On-chain deposit verification (Solana RPC, canonical mint only)
- Authenticated withdrawal queue
- Deposit/withdraw history
- Lightweight public bridge pages
"""

import json
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.request

from flask import Blueprint, g, jsonify, render_template, request

wrtc_bp = Blueprint("wrtc_bridge", __name__)

# Canonical wRTC settings from bounty spec.
WRTC_MINT = "12TAdKXxcGf6oCv4rqDz2NkgxjyHq6HQKoxKZYGf5i4X"
WRTC_DECIMALS = 6
WRTC_RESERVE_WALLET = "3n7RJanhRghRzW2PBg1UbkV9syiod8iUMugTvLzwTRkW"
WRTC_BUY_URL = (
    "https://raydium.io/swap/?inputMint=sol&outputMint="
    "12TAdKXxcGf6oCv4rqDz2NkgxjyHq6HQKoxKZYGf5i4X"
)

SOLANA_RPC_URL = os.environ.get("BOTTUBE_SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
WRTC_WITHDRAW_FEE = float(os.environ.get("BOTTUBE_WRTC_WITHDRAW_FEE", "0.05"))
WRTC_MIN_WITHDRAW = float(os.environ.get("BOTTUBE_WRTC_MIN_WITHDRAW", "1"))
WRTC_MAX_WITHDRAW = float(os.environ.get("BOTTUBE_WRTC_MAX_WITHDRAW", "100000"))

_SOLANA_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def get_db():
    """Get database connection from Flask g."""
    if "db" in g:
        return g.db
    db_path = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")
    g.db = sqlite3.connect(db_path)
    g.db.row_factory = sqlite3.Row
    return g.db


def init_wrtc_tables(db):
    """Create bridge tables if they don't exist."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS wrtc_deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_signature TEXT UNIQUE NOT NULL,
            agent_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,
            sender_address TEXT NOT NULL,
            reserve_address TEXT NOT NULL,
            mint TEXT NOT NULL,
            amount_raw TEXT NOT NULL,
            amount_wrtc REAL NOT NULL,
            slot INTEGER,
            block_time INTEGER,
            verified INTEGER DEFAULT 1,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_wrtc_deposits_agent_created
            ON wrtc_deposits(agent_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS wrtc_withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            withdrawal_id TEXT UNIQUE NOT NULL,
            agent_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,
            to_address TEXT NOT NULL,
            amount_wrtc REAL NOT NULL,
            fee_wrtc REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            tx_signature TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_wrtc_withdrawals_agent_created
            ON wrtc_withdrawals(agent_id, created_at DESC);
        """
    )
    db.commit()


def _rpc_call(method, params):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(
        SOLANA_RPC_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Solana RPC request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Solana RPC returned invalid JSON") from exc


def _raw_amount(token_balance):
    amt = (
        (token_balance or {})
        .get("uiTokenAmount", {})
        .get("amount", "0")
    )
    try:
        return int(amt)
    except (TypeError, ValueError):
        return 0


def verify_wrtc_transfer(tx_signature):
    """Verify transaction includes a canonical wRTC transfer into reserve wallet."""
    if not tx_signature:
        return None, "tx_signature is required"

    try:
        tx = _rpc_call(
            "getTransaction",
            [tx_signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        )
    except RuntimeError as exc:
        return None, str(exc)

    result = tx.get("result")
    if not result:
        return None, "Transaction not found or not finalized yet"

    meta = result.get("meta") or {}
    if meta.get("err"):
        return None, f"Transaction failed on-chain: {meta.get('err')}"

    pre_balances = meta.get("preTokenBalances") or []
    post_balances = meta.get("postTokenBalances") or []
    canonical_post = [b for b in post_balances if b.get("mint") == WRTC_MINT]

    if not canonical_post:
        return None, "No canonical wRTC mint transfer found in transaction"

    pre_by_index = {b.get("accountIndex"): b for b in pre_balances if b.get("mint") == WRTC_MINT}
    post_by_index = {b.get("accountIndex"): b for b in canonical_post}

    # Identify incoming amount to reserve token account.
    reserve_delta = 0
    for post_bal in canonical_post:
        if (post_bal.get("owner") or "") != WRTC_RESERVE_WALLET:
            continue
        account_index = post_bal.get("accountIndex")
        pre_bal = pre_by_index.get(account_index, {})
        delta = _raw_amount(post_bal) - _raw_amount(pre_bal)
        if delta > reserve_delta:
            reserve_delta = delta

    if reserve_delta <= 0:
        return None, "Canonical wRTC transfer to reserve wallet not found"

    # Infer sender by largest canonical-token decrease among non-reserve owners.
    sender_address = ""
    sender_delta = 0
    owner_deltas = {}
    for account_index, pre_bal in pre_by_index.items():
        owner = pre_bal.get("owner") or ""
        if not owner or owner == WRTC_RESERVE_WALLET:
            continue
        post_bal = post_by_index.get(account_index, {})
        dec = _raw_amount(pre_bal) - _raw_amount(post_bal)
        if dec > 0:
            owner_deltas[owner] = owner_deltas.get(owner, 0) + dec
    for owner, dec in owner_deltas.items():
        if dec > sender_delta:
            sender_address = owner
            sender_delta = dec

    if not sender_address:
        return None, "Could not determine sender address for canonical transfer"

    amount_wrtc = reserve_delta / float(10 ** WRTC_DECIMALS)
    return (
        {
            "tx_signature": tx_signature,
            "mint": WRTC_MINT,
            "reserve_address": WRTC_RESERVE_WALLET,
            "sender_address": sender_address,
            "amount_raw": str(reserve_delta),
            "amount_wrtc": amount_wrtc,
            "slot": result.get("slot"),
            "block_time": result.get("blockTime"),
        },
        None,
    )


def _get_authenticated_agent():
    api_key = (request.headers.get("X-API-Key") or "").strip()
    if not api_key:
        return None
    db = get_db()
    return db.execute(
        "SELECT id, agent_name, sol_address, rtc_balance FROM agents WHERE api_key = ?",
        (api_key,),
    ).fetchone()


@wrtc_bp.route("/api/wrtc-bridge/info", methods=["GET"])
def wrtc_bridge_info():
    db = get_db()
    init_wrtc_tables(db)

    dep = db.execute(
        """
        SELECT COUNT(*) AS deposits_count, COALESCE(SUM(amount_wrtc), 0) AS total_deposited
        FROM wrtc_deposits
        WHERE verified = 1
        """
    ).fetchone()
    wd = db.execute(
        """
        SELECT COUNT(*) AS withdrawals_count, COALESCE(SUM(amount_wrtc), 0) AS total_withdrawn
        FROM wrtc_withdrawals
        WHERE status IN ('queued', 'processing', 'sent', 'completed')
        """
    ).fetchone()

    return jsonify(
        {
            "network": "solana",
            "mint": WRTC_MINT,
            "decimals": WRTC_DECIMALS,
            "reserve_wallet": WRTC_RESERVE_WALLET,
            "buy_url": WRTC_BUY_URL,
            "limits": {
                "min_withdraw_wrtc": WRTC_MIN_WITHDRAW,
                "max_withdraw_wrtc": WRTC_MAX_WITHDRAW,
            },
            "fees": {
                "deposit_wrtc": 0.0,
                "withdraw_wrtc": WRTC_WITHDRAW_FEE,
            },
            "stats": {
                "deposits_count": dep["deposits_count"],
                "total_deposited_wrtc": dep["total_deposited"],
                "withdrawals_count": wd["withdrawals_count"],
                "total_withdrawn_wrtc": wd["total_withdrawn"],
            },
        }
    )


@wrtc_bp.route("/api/wrtc-bridge/deposit", methods=["POST"])
def wrtc_bridge_deposit():
    agent = _get_authenticated_agent()
    if not agent:
        return jsonify({"error": "Authentication required. Provide X-API-Key header."}), 401

    data = request.get_json(silent=True) or {}
    tx_signature = (data.get("tx_signature") or "").strip()
    if len(tx_signature) < 32:
        return jsonify({"error": "tx_signature is required"}), 400

    db = get_db()
    init_wrtc_tables(db)

    existing = db.execute(
        "SELECT * FROM wrtc_deposits WHERE tx_signature = ?",
        (tx_signature,),
    ).fetchone()
    if existing:
        if existing["agent_id"] != agent["id"]:
            return jsonify({"error": "tx_signature already claimed by another account"}), 409
        return jsonify(
            {
                "ok": True,
                "idempotent": True,
                "deposit": dict(existing),
            }
        )

    transfer, err = verify_wrtc_transfer(tx_signature)
    if not transfer:
        return jsonify({"error": f"Verification failed: {err}"}), 400

    # Anti-theft: sender must match the account's saved Solana address.
    account_sol = (agent["sol_address"] or "").strip()
    if not account_sol:
        return (
            jsonify(
                {
                    "error": (
                        "No Solana wallet bound to account. "
                        "Set your Solana wallet on profile before deposit verification."
                    )
                }
            ),
            400,
        )
    if account_sol != transfer["sender_address"]:
        return (
            jsonify(
                {
                    "error": "Sender wallet does not match the account's verified Solana wallet",
                    "expected_sender": account_sol,
                    "onchain_sender": transfer["sender_address"],
                }
            ),
            403,
        )

    db.execute(
        """
        INSERT INTO wrtc_deposits (
            tx_signature, agent_id, agent_name, sender_address, reserve_address, mint,
            amount_raw, amount_wrtc, slot, block_time, verified, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            transfer["tx_signature"],
            agent["id"],
            agent["agent_name"],
            transfer["sender_address"],
            transfer["reserve_address"],
            transfer["mint"],
            transfer["amount_raw"],
            transfer["amount_wrtc"],
            transfer["slot"],
            transfer["block_time"],
            time.time(),
        ),
    )
    db.execute(
        "UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?",
        (transfer["amount_wrtc"], agent["id"]),
    )
    db.commit()

    new_balance = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (agent["id"],)).fetchone()
    return jsonify(
        {
            "ok": True,
            "deposit": transfer,
            "credited_rtc": transfer["amount_wrtc"],
            "new_rtc_balance": new_balance["rtc_balance"],
        }
    )


@wrtc_bp.route("/api/wrtc-bridge/withdraw", methods=["POST"])
def wrtc_bridge_withdraw():
    agent = _get_authenticated_agent()
    if not agent:
        return jsonify({"error": "Authentication required. Provide X-API-Key header."}), 401

    data = request.get_json(silent=True) or {}
    to_address = (data.get("to_address") or "").strip()
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0.0

    if not _SOLANA_ADDR_RE.match(to_address):
        return jsonify({"error": "Valid Solana destination address is required"}), 400
    if amount < WRTC_MIN_WITHDRAW:
        return jsonify({"error": f"Minimum withdrawal is {WRTC_MIN_WITHDRAW} wRTC"}), 400
    if amount > WRTC_MAX_WITHDRAW:
        return jsonify({"error": f"Maximum withdrawal is {WRTC_MAX_WITHDRAW} wRTC"}), 400

    db = get_db()
    init_wrtc_tables(db)

    total_debit = round(amount + WRTC_WITHDRAW_FEE, WRTC_DECIMALS)
    balance = float(agent["rtc_balance"] or 0.0)
    if balance < total_debit:
        return (
            jsonify(
                {
                    "error": "Insufficient RTC balance",
                    "balance": balance,
                    "required": total_debit,
                }
            ),
            400,
        )

    now = time.time()
    withdrawal_id = f"wd_{int(now)}_{secrets.token_hex(4)}"
    db.execute(
        """
        INSERT INTO wrtc_withdrawals (
            withdrawal_id, agent_id, agent_name, to_address, amount_wrtc, fee_wrtc,
            status, tx_signature, note, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'queued', '', '', ?, ?)
        """,
        (withdrawal_id, agent["id"], agent["agent_name"], to_address, amount, WRTC_WITHDRAW_FEE, now, now),
    )
    db.execute(
        "UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?",
        (total_debit, agent["id"]),
    )
    db.commit()

    new_balance = db.execute("SELECT rtc_balance FROM agents WHERE id = ?", (agent["id"],)).fetchone()
    return jsonify(
        {
            "ok": True,
            "withdrawal": {
                "withdrawal_id": withdrawal_id,
                "to_address": to_address,
                "amount_wrtc": amount,
                "fee_wrtc": WRTC_WITHDRAW_FEE,
                "status": "queued",
            },
            "new_rtc_balance": new_balance["rtc_balance"],
        }
    )


@wrtc_bp.route("/api/wrtc-bridge/history", methods=["GET"])
def wrtc_bridge_history():
    agent = _get_authenticated_agent()
    if not agent:
        return jsonify({"error": "Authentication required. Provide X-API-Key header."}), 401

    limit = min(200, max(1, request.args.get("limit", 50, type=int)))
    db = get_db()
    init_wrtc_tables(db)

    deposits = db.execute(
        """
        SELECT
            tx_signature AS reference_id,
            amount_wrtc,
            sender_address,
            reserve_address,
            mint,
            created_at,
            'deposit' AS type,
            'verified' AS status
        FROM wrtc_deposits
        WHERE agent_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (agent["id"], limit),
    ).fetchall()
    withdrawals = db.execute(
        """
        SELECT
            withdrawal_id AS reference_id,
            amount_wrtc,
            to_address AS sender_address,
            '' AS reserve_address,
            ? AS mint,
            created_at,
            'withdraw' AS type,
            status
        FROM wrtc_withdrawals
        WHERE agent_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (WRTC_MINT, agent["id"], limit),
    ).fetchall()

    combined = [dict(row) for row in deposits] + [dict(row) for row in withdrawals]
    combined.sort(key=lambda row: row.get("created_at", 0), reverse=True)

    return jsonify(
        {
            "ok": True,
            "history": combined[:limit],
        }
    )


@wrtc_bp.route("/bridge")
def wrtc_bridge_landing():
    return render_template(
        "bridge.html",
        wrtc_mint=WRTC_MINT,
        wrtc_reserve_wallet=WRTC_RESERVE_WALLET,
        wrtc_buy_url=WRTC_BUY_URL,
    )


@wrtc_bp.route("/bridge/wrtc")
def wrtc_bridge_page():
    return render_template(
        "bridge_wrtc.html",
        wrtc_mint=WRTC_MINT,
        wrtc_reserve_wallet=WRTC_RESERVE_WALLET,
        wrtc_buy_url=WRTC_BUY_URL,
        wrtc_decimals=WRTC_DECIMALS,
    )
