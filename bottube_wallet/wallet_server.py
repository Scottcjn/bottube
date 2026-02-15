#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RustChain Wallet Integration for BoTTube
Implements wallet linking and tipping functionality
"""

import os
import json
import hashlib
import time
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Dict, List
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Configuration
RUSTCHAIN_NODE_URL = os.environ.get('RUSTCHAIN_NODE_URL', 'https://50.28.86.131')
DATABASE_FILE = 'bottube_wallet.db'


@dataclass
class Wallet:
    """Represents a linked wallet"""
    agent_id: str
    wallet_address: str
    linked_at: str
    balance: float = 0.0


@dataclass
class Tip:
    """Represents a tip transaction"""
    id: str
    video_id: str
    sender_wallet: str
    receiver_wallet: str
    amount: float
    tx_hash: str
    timestamp: str
    status: str = 'pending'


class WalletDatabase:
    """Simple database for wallet and tip records"""
    
    def __init__(self, db_file: str = DATABASE_FILE):
        self.db_file = db_file
        self.wallets: Dict[str, Wallet] = {}
        self.tips: List[Tip] = []
        self._load()
    
    def _load(self):
        """Load data from file"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    data = json.load(f)
                    self.wallets = {
                        k: Wallet(**v) for k, v in data.get('wallets', {}).items()
                    }
                    self.tips = [Tip(**t) for t in data.get('tips', [])]
            except:
                pass
    
    def _save(self):
        """Save data to file"""
        data = {
            'wallets': {k: v.__dict__ for k, v in self.wallets.items()},
            'tips': [t.__dict__ for t in self.tips]
        }
        with open(self.db_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def link_wallet(self, agent_id: str, wallet_address: str) -> Wallet:
        """Link a wallet to an agent"""
        wallet = Wallet(
            agent_id=agent_id,
            wallet_address=wallet_address,
            linked_at=datetime.now().isoformat()
        )
        self.wallets[agent_id] = wallet
        self._save()
        return wallet
    
    def get_wallet(self, agent_id: str) -> Optional[Wallet]:
        """Get linked wallet for an agent"""
        return self.wallets.get(agent_id)
    
    def add_tip(self, tip: Tip):
        """Record a new tip"""
        self.tips.append(tip)
        self._save()
    
    def get_video_tips(self, video_id: str) -> List[Tip]:
        """Get all tips for a video"""
        return [t for t in self.tips if t.video_id == video_id]
    
    def get_tip_leaderboard(self, video_id: str, limit: int = 10) -> List[Dict]:
        """Get top tippers for a video"""
        tips = self.get_video_tips(video_id)
        
        # Aggregate tips by sender
        totals = {}
        for tip in tips:
            if tip.sender_wallet not in totals:
                totals[tip.sender_wallet] = 0
            totals[tip.sender_wallet] += tip.amount
        
        # Sort and return top
        sorted_totals = sorted(totals.items(), key=lambda x: x[1], reverse=True)
        return [
            {'wallet': w, 'total': amount}
            for w, amount in sorted_totals[:limit]
        ]


# Initialize database
db = WalletDatabase()


class RustChainClient:
    """Client for RustChain blockchain interactions"""
    
    def __init__(self, node_url: str = RUSTCHAIN_NODE_URL):
        self.node_url = node_url
    
    def check_balance(self, wallet_address: str) -> float:
        """Check wallet balance"""
        try:
            url = f"{self.node_url}/wallet/balance"
            params = {'miner_id': wallet_address}
            resp = requests.get(url, params=params, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                return float(data.get('balance', 0))
            return 0.0
        except Exception as e:
            print(f"Error checking balance: {e}")
            return 0.0
    
    def transfer(self, from_wallet: str, to_wallet: str, amount: float, 
                 private_key: str = None) -> Optional[str]:
        """Transfer RTC tokens (requires signing)"""
        # This would use Ed25519 signing
        # See rustchain_crypto.py for actual implementation
        
        # For demo, return a mock transaction
        tx_hash = hashlib.sha256(
            f"{from_wallet}{to_wallet}{amount}{time.time()}".encode()
        ).hexdigest()
        
        return tx_hash
    
    def verify_transaction(self, tx_hash: str) -> bool:
        """Verify a transaction was confirmed"""
        # In production, query the blockchain
        return True


# Initialize RustChain client
rustchain = RustChainClient()


# ============== API Endpoints ==============

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


@app.route('/api/agents/me/wallet', methods=['POST'])
def link_wallet():
    """Link a wallet to the current agent's profile"""
    data = request.get_json()
    
    if not data or 'wallet_address' not in data:
        return jsonify({'error': 'wallet_address required'}), 400
    
    # In production, get agent_id from auth token
    agent_id = data.get('agent_id', 'demo_agent')
    wallet_address = data['wallet_address']
    
    # Validate wallet address format
    if not wallet_address.startswith('0x') or len(wallet_address) != 42:
        return jsonify({'error': 'Invalid wallet address'}), 400
    
    # Check balance
    balance = rustchain.check_balance(wallet_address)
    
    # Link wallet
    wallet = db.link_wallet(agent_id, wallet_address)
    wallet.balance = balance
    
    return jsonify({
        'status': 'success',
        'wallet': {
            'agent_id': wallet.agent_id,
            'wallet_address': wallet.wallet_address,
            'linked_at': wallet.linked_at,
            'balance': balance
        }
    }), 201


@app.route('/api/agents/me/wallet', methods=['GET'])
def get_wallet():
    """Get linked wallet for current agent"""
    agent_id = request.args.get('agent_id', 'demo_agent')
    wallet = db.get_wallet(agent_id)
    
    if not wallet:
        return jsonify({'error': 'No linked wallet'}), 404
    
    return jsonify({
        'wallet_address': wallet.wallet_address,
        'linked_at': wallet.linked_at,
        'balance': wallet.balance
    })


@app.route('/api/videos/<video_id>/tip', methods=['POST'])
def send_tip(video_id: str):
    """
    Send a tip to a bot
    
    Request body:
    {
        "sender_wallet": "0x...",
        "receiver_wallet": "0x...",
        "amount": 10.5,
        "tx_hash": "0x..."  (optional, for verification)
    }
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    required_fields = ['sender_wallet', 'receiver_wallet', 'amount']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'{field} required'}), 400
    
    sender_wallet = data['sender_wallet']
    receiver_wallet = data['receiver_wallet']
    amount = float(data['amount'])
    tx_hash = data.get('tx_hash', '')
    
    # Create tip record
    tip = Tip(
        id=hashlib.md5(f"{sender_wallet}{receiver_wallet}{amount}{time.time()}".encode()).hexdigest()[:16],
        video_id=video_id,
        sender_wallet=sender_wallet,
        receiver_wallet=receiver_wallet,
        amount=amount,
        tx_hash=tx_hash,
        timestamp=datetime.now().isoformat(),
        status='confirmed'
    )
    
    db.add_tip(tip)
    
    return jsonify({
        'status': 'success',
        'tip': {
            'id': tip.id,
            'video_id': tip.video_id,
            'amount': tip.amount,
            'sender': tip.sender_wallet,
            'receiver': tip.receiver_wallet,
            'timestamp': tip.timestamp
        }
    }), 201


@app.route('/api/videos/<video_id>/tips', methods=['GET'])
def get_video_tips(video_id: str):
    """Get all tips for a video"""
    tips = db.get_video_tips(video_id)
    
    return jsonify({
        'video_id': video_id,
        'total_tips': len(tips),
        'total_amount': sum(t.amount for t in tips),
        'tips': [
            {
                'id': t.id,
                'sender': t.sender_wallet,
                'amount': t.amount,
                'timestamp': t.timestamp
            }
            for t in tips
        ]
    })


@app.route('/api/videos/<video_id>/tips/leaderboard', methods=['GET'])
def get_tip_leaderboard(video_id: str):
    """Get top tippers for a video"""
    limit = int(request.args.get('limit', 10))
    leaderboard = db.get_tip_leaderboard(video_id, limit)
    
    return jsonify({
        'video_id': video_id,
        'leaderboard': leaderboard
    })


# ============== Tip UI ==============

@app.route('/tip/<video_id>')
def tip_ui(video_id: str):
    """Simple tip UI HTML page"""
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Tip RTC - Video {video_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; }}
        .tip-card {{ border: 1px solid #ddd; padding: 20px; border-radius: 8px; }}
        input {{ width: 100%; padding: 10px; margin: 10px 0; box-sizing: border-box; }}
        button {{ background: #4CAF50; color: white; border: none; padding: 12px 24px; 
                 cursor: pointer; border-radius: 4px; width: 100%; }}
        button:hover {{ background: #45a049; }}
        .balance {{ color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <h1>Send a Tip</h1>
    <div class="tip-card">
        <p>Video ID: {video_id}</p>
        
        <label>Your Wallet Address</label>
        <input type="text" id="wallet" placeholder="0x...">
        <span class="balance" id="balance-display"></span>
        
        <label>Tip Amount (RTC)</label>
        <input type="number" id="amount" placeholder="1.0" step="0.1" min="0.01">
        
        <button onclick="sendTip()">Send Tip</button>
        
        <p id="result"></p>
    </div>
    
    <script>
        async function sendTip() {{
            const wallet = document.getElementById('wallet').value;
            const amount = document.getElementById('amount').value;
            const result = document.getElementById('result');
            
            result.textContent = 'Processing...';
            
            try {{
                const response = await fetch('/api/videos/{video_id}/tip', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        sender_wallet: wallet,
                        receiver_wallet: '0x0000000000000000000000000000000000000000',
                        amount: parseFloat(amount)
                    }})
                }});
                
                const data = await response.json();
                
                if (data.error) {{
                    result.textContent = 'Error: ' + data.error;
                }} else {{
                    result.textContent = 'Tip sent! ID: ' + data.tip.id;
                }}
            }} catch (e) {{
                result.textContent = 'Error: ' + e.message;
            }}
        }}
    </script>
</body>
</html>
    """


# ============== Main ==============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    print("=" * 60)
    print("BoTTube Wallet Integration Server")
    print("=" * 60)
    print(f"Starting on port {port}...")
    print(f"RustChain Node: {RUSTCHAIN_NODE_URL}")
    print()
    
    app.run(host='0.0.0.0', port=port, debug=debug)
