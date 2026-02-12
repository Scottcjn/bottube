#!/usr/bin/env python3
"""
BoTTube Banano Payout Processor
Cron script to process pending BAN withdrawals using bananopie.

Uses bananopie library for correct Ed25519-Blake2b block signing.
Constructs proper state blocks and submits via 'process' RPC.

Usage:
    */5 * * * * cd /root/bottube && python3 banano_payout.py >> /var/log/banano_payout.log 2>&1
"""

import json
import os
import sqlite3
import sys
import time
import urllib.request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")
KALIUM_API = "https://kaliumapi.appditto.com/api"
KALIUM_FALLBACK = "https://public.node.jungletv.live/rpc"
BANANO_SEED = os.environ.get("BANANO_SEED", "")
BAN_RAW_MULTIPLIER = 10**29

# Platform hot wallet is index 0
PLATFORM_WALLET_INDEX = 0

# Try importing bananopie
try:
    from bananopie import RPC as BananoRPC, Wallet as BananoWallet, whole_to_raw, raw_to_whole
    HAS_BANANOPIE = True
except ImportError:
    HAS_BANANOPIE = False


def log(level, msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def _ban_rpc(action_data: dict) -> dict:
    """Send an RPC request with fallback."""
    for api_url in [KALIUM_API, KALIUM_FALLBACK]:
        try:
            payload = json.dumps(action_data).encode()
            req = urllib.request.Request(
                api_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                if "error" not in result:
                    return result
                if api_url == KALIUM_FALLBACK:
                    return result
        except Exception as e:
            if api_url == KALIUM_FALLBACK:
                return {"error": str(e)}
    return {"error": "all RPC endpoints failed"}


def process_withdrawals():
    """Process all pending BAN withdrawals."""
    if not BANANO_SEED:
        log("WARN", "BANANO_SEED not set, skipping")
        return

    if not HAS_BANANOPIE:
        log("ERROR", "bananopie not installed. Install with: pip install bananopie")
        return

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    pending = db.execute(
        "SELECT bt.*, bw.account_index FROM ban_transactions bt "
        "LEFT JOIN ban_wallets bw ON bt.agent_id = bw.agent_id "
        "WHERE bt.status = 'pending' AND bt.tx_type = 'withdrawal' "
        "ORDER BY bt.created_at ASC LIMIT 10"
    ).fetchall()

    if not pending:
        db.close()
        return

    # Create bananopie wallet for platform hot wallet (index 0)
    rpc = BananoRPC(KALIUM_API)
    wallet = BananoWallet(rpc, seed=BANANO_SEED, index=PLATFORM_WALLET_INDEX)
    platform_address = wallet.get_address()

    log("INFO", f"Processing {len(pending)} pending withdrawals from {platform_address}")

    # First, receive any pending deposits to ensure balance is available
    try:
        wallet.receive_all()
        log("INFO", "Received all pending deposits")
    except Exception as e:
        log("WARN", f"receive_all failed (may be no pending): {e}")

    # Check on-chain balance
    try:
        balance_info = rpc.get_account_balance(platform_address)
        balance_raw = int(balance_info.get("balance", "0"))
        balance_ban = balance_raw / BAN_RAW_MULTIPLIER
        log("INFO", f"Platform balance: {balance_ban:.4f} BAN")
    except Exception as e:
        log("ERROR", f"Could not check balance: {e}")
        db.close()
        return

    for tx in pending:
        tx_id = tx["id"]
        amount_ban = tx["amount_ban"]
        reason = tx["reason"]

        # Extract destination address from reason field
        to_address = ""
        if reason.startswith("withdraw_to_"):
            to_address = reason[len("withdraw_to_"):]

        if not to_address or not to_address.startswith("ban_"):
            log("WARN", f"TX#{tx_id}: Invalid destination in reason: {reason}")
            db.execute(
                "UPDATE ban_transactions SET status = 'failed', processed_at = ? WHERE id = ?",
                (time.time(), tx_id),
            )
            db.commit()
            continue

        # Check if we have enough balance
        if balance_ban < amount_ban:
            log("ERROR", f"TX#{tx_id}: Insufficient platform balance "
                f"({balance_ban:.4f} < {amount_ban:.4f}). Stopping.")
            break

        log("INFO", f"TX#{tx_id}: Sending {amount_ban} BAN to {to_address}")

        try:
            # bananopie.Wallet.send() constructs a proper state block:
            # 1. Fetches account_info for frontier + current balance
            # 2. Computes new_balance = current_balance - amount_raw
            # 3. Constructs state block with link = recipient public key
            # 4. Signs with Ed25519-Blake2b (correct for Banano)
            # 5. Computes PoW (locally or via RPC)
            # 6. Submits via 'process' RPC
            block_hash = wallet.send(to_address, str(amount_ban))

            log("OK", f"TX#{tx_id}: Sent! Block: {block_hash}")
            db.execute(
                "UPDATE ban_transactions SET status = 'sent', block_hash = ?, processed_at = ? WHERE id = ?",
                (str(block_hash), time.time(), tx_id),
            )
            balance_ban -= amount_ban

        except Exception as e:
            error_str = str(e)
            log("ERROR", f"TX#{tx_id}: Failed - {error_str}")

            # Mark as failed only for permanent errors
            if any(kw in error_str.lower() for kw in ["insufficient", "invalid", "bad", "fork"]):
                db.execute(
                    "UPDATE ban_transactions SET status = 'failed', processed_at = ? WHERE id = ?",
                    (time.time(), tx_id),
                )
            # Otherwise leave as pending for retry on next cron run

        db.commit()
        time.sleep(1)  # Rate limit between sends

    db.close()
    log("INFO", "Payout processing complete")


def check_balance():
    """Quick balance check utility."""
    if not BANANO_SEED:
        print("BANANO_SEED not set")
        return

    if HAS_BANANOPIE:
        rpc = BananoRPC(KALIUM_API)
        wallet = BananoWallet(rpc, seed=BANANO_SEED, index=0)
        address = wallet.get_address()
    else:
        import hashlib
        seed_bytes = bytes.fromhex(BANANO_SEED)
        index_bytes = (0).to_bytes(4, "big")
        private_key = hashlib.blake2b(seed_bytes + index_bytes, digest_size=32).hexdigest()
        resp = _ban_rpc({"action": "key_expand", "key": private_key})
        address = resp.get("account", "unknown")

    resp = _ban_rpc({"action": "account_balance", "account": address})
    balance_raw = int(resp.get("balance", "0"))
    receivable_raw = int(resp.get("receivable", resp.get("pending", "0")))

    print(f"Platform wallet: {address}")
    print(f"Balance:    {balance_raw / BAN_RAW_MULTIPLIER:.4f} BAN")
    print(f"Receivable: {receivable_raw / BAN_RAW_MULTIPLIER:.4f} BAN")
    print(f"bananopie:  {'available' if HAS_BANANOPIE else 'NOT INSTALLED'}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "balance":
        check_balance()
    else:
        process_withdrawals()
