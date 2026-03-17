#!/usr/bin/env python3
"""
RTC Mobile Wallet App - Backend API
Implements:
- Balance check
- Transaction history
- QR receive address
- Send transaction
"""

import json
import time
import hashlib
import secrets
from typing import Dict, List, Optional
from flask import jsonify, request

# ── Mock Wallet Data ──

def generate_wallet_address() -> str:
    """Generate a mock RTC wallet address."""
    return "RTC" + hashlib.sha256(secrets.token_bytes(32)).hexdigest()[:40]

def get_wallet_balance(db, agent_id: int) -> Dict:
    """Get wallet balance for an agent."""
    
    balance = db.execute("""
        SELECT COALESCE(SUM(amount), 0) as balance
        FROM quest_completions
        WHERE agent_id = ? AND status = 'confirmed'
    """, (agent_id,)).fetchone()["balance"]
    
    pending = db.execute("""
        SELECT COALESCE(SUM(rtc_earned), 0) as pending
        FROM quest_completions
        WHERE agent_id = ? AND status = 'pending'
    """, (agent_id,)).fetchone()["pending"]
    
    return {
        "available": balance,
        "pending": pending,
        "total": balance + pending
    }

def get_transaction_history(db, agent_id: int, limit: int = 20) -> List[Dict]:
    """Get transaction history for an agent."""
    
    txs = db.execute("""
        SELECT 
            qc.id, qc.quest_id, qc.rtc_earned, qc.xp_earned,
            qc.completed_at, qc.confirms_at, qc.status,
            q.name as quest_name
        FROM quest_completions qc
        LEFT JOIN quests q ON qc.quest_id = q.id
        WHERE qc.agent_id = ?
        ORDER BY qc.completed_at DESC
        LIMIT ?
    """, (agent_id, limit)).fetchall()
    
    result = []
    for tx in txs:
        result.append({
            "id": tx["id"],
            "type": "quest_reward",
            "quest_id": tx["quest_id"],
            "quest_name": tx["quest_name"],
            "amount": tx["rtc_earned"],
            "xp_earned": tx["xp_earned"],
            "status": tx["status"],
            "completed_at": tx["completed_at"],
            "confirms_at": tx["confirms_at"]
        })
    
    return result

def get_receive_address(db, agent_id: int) -> str:
    """Get or create receive address for an agent."""
    
    address = db.execute("""
        SELECT wallet_address FROM agent_wallets
        WHERE agent_id = ?
    """, (agent_id,)).fetchone()
    
    if not address:
        new_address = generate_wallet_address()
        db.execute("""
            INSERT INTO agent_wallets (agent_id, wallet_address, created_at)
            VALUES (?, ?, ?)
        """, (agent_id, new_address, time.time()))
        db.commit()
        return new_address
    
    return address["wallet_address"]

# ── API Route Registration ──

def register_wallet_routes(app):
    """Register wallet routes with the Flask app."""
    
    @app.route("/api/wallet/balance")
    def get_balance():
        """Get wallet balance."""
        balance = get_wallet_balance(g.db, g.agent["id"])
        return jsonify({"ok": True, "balance": balance})
    
    @app.route("/api/wallet/transactions")
    def get_transactions():
        """Get transaction history."""
        limit = min(int(request.args.get("limit", 20)), 100)
        txs = get_transaction_history(g.db, g.agent["id"], limit)
        return jsonify({"ok": True, "transactions": txs, "count": len(txs)})
    
    @app.route("/api/wallet/address")
    def get_address():
        """Get receive address."""
        address = get_receive_address(g.db, g.agent["id"])
        return jsonify({"ok": True, "address": address})
    
    @app.route("/api/wallet/qr")
    def get_qr():
        """Get QR code for receive address."""
        address = get_receive_address(g.db, g.agent["id"])
        qr_data = f"rtc:{address}"
        return jsonify({
            "ok": True,
            "address": address,
            "qr_data": qr_data,
            "qr_image": f"https://api.qrserver.com/v1/create-qr-code/?data={qr_data}&size=256x256"
        })
    
    @app.route("/api/wallet/send", methods=["POST"])
    def send_transaction():
        """Send RTC to another address."""
        data = request.get_json()
        to_address = data.get("to_address")
        amount = data.get("amount")
        
        if not to_address or not amount:
            return jsonify({"error": "to_address and amount required"}), 400
        
        # Check balance
        balance = get_wallet_balance(g.db, g.agent["id"])
        if balance["available"] < amount:
            return jsonify({"error": "Insufficient balance"}), 400
        
        # Create transaction record
        tx_hash = hashlib.sha256(
            f"{g.agent['id']}:{to_address}:{amount}:{time.time()}".encode()
        ).hexdigest()
        
        db.execute("""
            INSERT INTO transactions
            (from_agent_id, to_address, amount, tx_hash, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, (g.agent["id"], to_address, amount, tx_hash, time.time()))
        db.commit()
        
        return jsonify({
            "ok": True,
            "tx_hash": tx_hash,
            "status": "pending",
            "message": f"Sent {amount} RTC to {to_address}"
        })

# ── Schema Info ──

WALLET_SCHEMA = """
-- Agent wallets table
CREATE TABLE IF NOT EXISTS agent_wallets (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER UNIQUE NOT NULL,
    wallet_address TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

-- Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    from_agent_id INTEGER NOT NULL,
    to_address TEXT NOT NULL,
    amount REAL NOT NULL,
    tx_hash TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at REAL NOT NULL,
    confirmed_at REAL,
    FOREIGN KEY (from_agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_transactions_from ON transactions(from_agent_id);
CREATE INDEX IF NOT EXISTS idx_transactions_hash ON transactions(tx_hash);
"""

