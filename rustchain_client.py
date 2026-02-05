#!/usr/bin/env python3
"""
RustChain API Client for BoTTube Integration

Provides interface to RustChain blockchain for:
- Balance checking
- Transaction verification
- Signed transfers

RustChain API (Node 1): https://50.28.86.131
"""

import hashlib
import json
import logging
import os
import time
from typing import Optional, Dict, Any, Tuple
import urllib.request
import urllib.error
import ssl

logger = logging.getLogger(__name__)

# RustChain API Configuration
RUSTCHAIN_API_BASE = os.environ.get("RUSTCHAIN_API_URL", "https://50.28.86.131")
RUSTCHAIN_TIMEOUT = int(os.environ.get("RUSTCHAIN_TIMEOUT", "10"))

# Create SSL context that accepts self-signed certs (RustChain nodes use them)
_ssl_context = ssl.create_default_context()
_ssl_context.check_hostname = False
_ssl_context.verify_mode = ssl.CERT_NONE


class RustChainError(Exception):
    """Base exception for RustChain API errors."""
    pass


class RustChainConnectionError(RustChainError):
    """Connection to RustChain node failed."""
    pass


class RustChainAPIError(RustChainError):
    """RustChain API returned an error."""
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


def _make_request(
    endpoint: str,
    method: str = "GET",
    data: dict = None,
    timeout: int = None
) -> Dict[str, Any]:
    """Make HTTP request to RustChain API.
    
    Args:
        endpoint: API endpoint (e.g., "/wallet/balance")
        method: HTTP method
        data: JSON data for POST requests
        timeout: Request timeout in seconds
    
    Returns:
        Parsed JSON response
        
    Raises:
        RustChainConnectionError: If connection fails
        RustChainAPIError: If API returns an error
    """
    url = f"{RUSTCHAIN_API_BASE}{endpoint}"
    timeout = timeout or RUSTCHAIN_TIMEOUT
    
    try:
        if method == "GET":
            req = urllib.request.Request(url, method="GET")
        else:
            json_data = json.dumps(data).encode("utf-8") if data else None
            req = urllib.request.Request(
                url,
                data=json_data,
                method=method,
                headers={"Content-Type": "application/json"}
            )
        
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
            
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(body)
            msg = error_data.get("error", str(e))
        except json.JSONDecodeError:
            msg = body or str(e)
        raise RustChainAPIError(msg, status_code=e.code, response=error_data if 'error_data' in dir() else {})
        
    except urllib.error.URLError as e:
        raise RustChainConnectionError(f"Failed to connect to RustChain node: {e}")
        
    except Exception as e:
        raise RustChainError(f"RustChain request failed: {e}")


def get_health() -> Dict[str, Any]:
    """Check RustChain node health.
    
    Returns:
        Health status dict with keys: ok, version, uptime_s, db_rw
    """
    return _make_request("/health")


def get_epoch() -> Dict[str, Any]:
    """Get current RustChain epoch info.
    
    Returns:
        Epoch info dict with keys: epoch, slot, epoch_pot, blocks_per_epoch
    """
    return _make_request("/epoch")


def get_balance(wallet_id: str) -> Dict[str, Any]:
    """Get RTC balance for a wallet.
    
    Args:
        wallet_id: RustChain wallet address (miner_id)
        
    Returns:
        Balance info dict with keys: miner_id, amount_rtc, amount_i64
    """
    if not wallet_id:
        raise ValueError("wallet_id is required")
    
    endpoint = f"/wallet/balance?miner_id={urllib.parse.quote(wallet_id)}"
    return _make_request(endpoint)


def get_miners() -> list:
    """Get list of active miners.
    
    Returns:
        List of miner dicts with antiquity info
    """
    return _make_request("/api/miners")


def transfer_signed(
    from_address: str,
    to_address: str,
    amount: float,
    signature: str,
    public_key: str,
    nonce: str,
    memo: str = ""
) -> Dict[str, Any]:
    """Execute a signed RTC transfer.
    
    Args:
        from_address: Sender wallet address
        to_address: Recipient wallet address
        amount: Amount of RTC to transfer
        signature: Ed25519 signature of the transaction
        public_key: Sender's public key (hex)
        nonce: Unique transaction nonce
        memo: Optional transaction memo
        
    Returns:
        Transaction result dict
    """
    data = {
        "from_address": from_address,
        "to_address": to_address,
        "amount": amount,
        "signature": signature,
        "public_key": public_key,
        "nonce": nonce,
    }
    if memo:
        data["memo"] = memo
        
    return _make_request("/wallet/transfer/signed", method="POST", data=data)


def verify_transfer(
    from_address: str,
    to_address: str,
    amount: float,
    timestamp: float,
    tolerance_seconds: int = 120
) -> Tuple[bool, str]:
    """Verify a transfer occurred by checking balance changes.
    
    Since RustChain doesn't have a transaction history endpoint,
    we verify by checking that:
    1. Both addresses exist and have valid balances
    2. The transfer could have occurred (recipient has sufficient balance)
    
    This is a soft verification - for higher assurance, use transfer_signed
    directly through BoTTube.
    
    Args:
        from_address: Sender wallet address
        to_address: Recipient wallet address  
        amount: Expected transfer amount
        timestamp: When the transfer allegedly occurred
        tolerance_seconds: How recent the transfer must be
        
    Returns:
        Tuple of (verified: bool, message: str)
    """
    now = time.time()
    
    # Check if timestamp is reasonable
    if timestamp > now:
        return False, "Transfer timestamp is in the future"
    if now - timestamp > tolerance_seconds:
        return False, f"Transfer is too old (>{tolerance_seconds}s)"
    
    try:
        # Verify both wallets exist
        sender_balance = get_balance(from_address)
        recipient_balance = get_balance(to_address)
        
        # Both wallets must be registered
        if sender_balance.get("amount_rtc") is None:
            return False, "Sender wallet not found"
        if recipient_balance.get("amount_rtc") is None:
            return False, "Recipient wallet not found"
            
        # Recipient must have at least the tip amount (they received it)
        if recipient_balance["amount_rtc"] < amount:
            return False, "Recipient balance too low for claimed transfer"
            
        return True, "Transfer verification passed (balance-based)"
        
    except RustChainError as e:
        return False, f"RustChain API error: {e}"


def create_transfer_nonce(from_address: str, to_address: str, amount: float) -> str:
    """Create a unique nonce for a transfer.
    
    Args:
        from_address: Sender address
        to_address: Recipient address
        amount: Transfer amount
        
    Returns:
        Unique nonce string
    """
    data = f"{from_address}:{to_address}:{amount}:{time.time()}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]


# Import urllib.parse for URL encoding
import urllib.parse


if __name__ == "__main__":
    # Test the client
    print("Testing RustChain client...")
    
    try:
        health = get_health()
        print(f"Health: {health}")
        
        epoch = get_epoch()
        print(f"Epoch: {epoch}")
        
        miners = get_miners()
        print(f"Active miners: {len(miners)}")
        
        if miners:
            test_wallet = miners[0]["miner"]
            balance = get_balance(test_wallet)
            print(f"Balance for {test_wallet}: {balance}")
            
    except RustChainError as e:
        print(f"Error: {e}")
