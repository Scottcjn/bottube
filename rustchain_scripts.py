#!/usr/bin/env python3
"""
RustChain Utility Scripts Collection
Implements:
- RTC price checker
- Mining profitability calculator
- Wallet address validator
- Transaction fee estimator
- Block explorer utils
"""

import json
import time
import hashlib
import random
from typing import Dict, List, Optional

# ── Mock Data ──

RTC_PRICE_USD = 0.10  # Mock price

def get_rtc_price() -> Dict:
    """Get current RTC price."""
    return {
        "price_usd": RTC_PRICE_USD,
        "price_btc": 0.0000025,
        "price_eth": 0.000045,
        "market_cap": 10000000,
        "volume_24h": 500000,
        "change_24h": 5.2,
        "updated_at": time.time()
    }

def calculate_mining_profitability(hash_rate: float, power_watts: float, 
                                    electricity_cost: float) -> Dict:
    """Calculate mining profitability."""
    
    # Mock calculations
    blocks_per_day = 144
    rtc_per_block = 50
    total_hash_rate = 1000000000  # 1 GH/s network
    
    my_share = hash_rate / total_hash_rate
    daily_rtc = blocks_per_day * rtc_per_block * my_share
    daily_revenue_usd = daily_rtc * RTC_PRICE_USD
    
    daily_power_kwh = power_watts * 24 / 1000
    daily_power_cost = daily_power_kwh * electricity_cost
    
    daily_profit = daily_revenue_usd - daily_power_cost
    monthly_profit = daily_profit * 30
    yearly_profit = daily_profit * 365
    
    roi_days = (power_watts * 0.05) / daily_profit if daily_profit > 0 else float('inf')
    
    return {
        "hash_rate": hash_rate,
        "power_watts": power_watts,
        "electricity_cost": electricity_cost,
        "daily_rtc": daily_rtc,
        "daily_revenue_usd": daily_revenue_usd,
        "daily_power_cost": daily_power_cost,
        "daily_profit": daily_profit,
        "monthly_profit": monthly_profit,
        "yearly_profit": yearly_profit,
        "roi_days": roi_days
    }

def validate_wallet_address(address: str) -> Dict:
    """Validate RTC wallet address."""
    
    if not address.startswith("RTC"):
        return {"valid": False, "error": "Address must start with 'RTC'"}
    
    if len(address) != 43:
        return {"valid": False, "error": "Address must be 43 characters"}
    
    hex_part = address[3:]
    try:
        int(hex_part, 16)
        return {"valid": True, "address": address, "type": "standard"}
    except ValueError:
        return {"valid": False, "error": "Invalid hex characters"}

def estimate_transaction_fee(amount: float, priority: str = "standard") -> Dict:
    """Estimate transaction fee."""
    
    fee_rates = {
        "low": 0.001,
        "standard": 0.005,
        "high": 0.01,
        "priority": 0.02
    }
    
    fee_rate = fee_rates.get(priority, 0.005)
    fee = amount * fee_rate
    fee = max(fee, 0.01)  # Minimum fee
    fee = min(fee, 10)    # Maximum fee
    
    confirmation_times = {
        "low": "60-120 minutes",
        "standard": "10-30 minutes",
        "high": "5-10 minutes",
        "priority": "1-5 minutes"
    }
    
    return {
        "amount": amount,
        "priority": priority,
        "fee_rtc": fee,
        "fee_usd": fee * RTC_PRICE_USD,
        "total": amount + fee,
        "estimated_confirmation": confirmation_times[priority]
    }

def get_block_info(block_number: int) -> Dict:
    """Get block information."""
    
    # Mock block data
    return {
        "number": block_number,
        "hash": hashlib.sha256(f"block-{block_number}".encode()).hexdigest(),
        "timestamp": time.time() - (1000 - block_number) * 60,
        "transactions": random.randint(50, 200),
        "miner": f"RTC{hashlib.sha256(f'miner-{block_number}'.encode()).hexdigest()[:40]}",
        "reward": 50,
        "size": random.randint(100000, 500000),
        "gas_used": random.randint(1000000, 5000000),
        "gas_limit": 8000000
    }

def get_recent_blocks(limit: int = 10) -> List[Dict]:
    """Get recent blocks."""
    current_block = 1000000
    return [get_block_info(current_block - i) for i in range(limit)]

def get_network_stats() -> Dict:
    """Get network statistics."""
    return {
        "block_height": 1000000,
        "total_transactions": 5000000,
        "total_addresses": 100000,
        "hash_rate": 1000000000,
        "difficulty": 15000000,
        "avg_block_time": 60,
        "avg_transaction_fee": 0.005,
        "rtc_price_usd": RTC_PRICE_USD,
        "market_cap": 10000000,
        "updated_at": time.time()
    }

# ── API Route Registration ──

def register_rustchain_routes(app):
    """Register RustChain utility routes."""
    
    @app.route("/api/rustchain/price")
    def get_price():
        """Get RTC price."""
        return jsonify({"ok": True, "price": get_rtc_price()})
    
    @app.route("/api/rustchain/mining/profitability")
    def get_profitability():
        """Calculate mining profitability."""
        hash_rate = float(request.args.get("hash_rate", 1000000))
        power = float(request.args.get("power", 500))
        electricity = float(request.args.get("electricity", 0.12))
        
        profit = calculate_mining_profitability(hash_rate, power, electricity)
        return jsonify({"ok": True, "profitability": profit})
    
    @app.route("/api/rustchain/address/validate")
    def validate_address():
        """Validate wallet address."""
        address = request.args.get("address", "")
        result = validate_wallet_address(address)
        return jsonify(result)
    
    @app.route("/api/rustchain/fee/estimate")
    def estimate_fee():
        """Estimate transaction fee."""
        amount = float(request.args.get("amount", 100))
        priority = request.args.get("priority", "standard")
        
        estimate = estimate_transaction_fee(amount, priority)
        return jsonify({"ok": True, "estimate": estimate})
    
    @app.route("/api/rustchain/block/<int:block_number>")
    def get_block(block_number):
        """Get block info."""
        block = get_block_info(block_number)
        return jsonify({"ok": True, "block": block})
    
    @app.route("/api/rustchain/blocks/recent")
    def get_recent_blocks_route():
        """Get recent blocks."""
        limit = min(int(request.args.get("limit", 10)), 50)
        blocks = get_recent_blocks(limit)
        return jsonify({"ok": True, "blocks": blocks, "count": len(blocks)})
    
    @app.route("/api/rustchain/network/stats")
    def get_network_stats_route():
        """Get network statistics."""
        stats = get_network_stats()
        return jsonify({"ok": True, "stats": stats})

# ── Schema Info ──

RUSTCHAIN_SCHEMA_INFO = """
RustChain Utility Scripts - No schema changes required.

Uses existing tables:
- agents (for address validation)
- transactions (for fee estimation)

New API Endpoints:
- GET /api/rustchain/price - Get RTC price
- GET /api/rustchain/mining/profitability - Mining calculator
- GET /api/rustchain/address/validate - Address validator
- GET /api/rustchain/fee/estimate - Fee estimator
- GET /api/rustchain/block/<n> - Block info
- GET /api/rustchain/blocks/recent - Recent blocks
- GET /api/rustchain/network/stats - Network stats
"""

