import aiohttp
import asyncio
import json
import time
import hmac
import hashlib
from typing import Dict, List, Any, Optional, Union
import logging

class RustChainError(Exception):
    """Base error for RustChain SDK"""
    pass

class RustChainClient:
    """
    Async client for RustChain node API.
    """
    def __init__(self, base_url: str = "https://50.28.86.131", verify_ssl: bool = False, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.logger = logging.getLogger("rustchain_sdk")

    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                async with session.request(
                    method, 
                    url, 
                    params=params, 
                    json=data, 
                    ssl=self.verify_ssl
                ) as resp:
                    if resp.status >= 400:
                        try:
                            err_data = await resp.json()
                            msg = err_data.get("error", await resp.text())
                        except:
                            msg = await resp.text()
                        raise RustChainError(f"HTTP {resp.status}: {msg}")
                    
                    return await resp.json()
            except aiohttp.ClientError as e:
                raise RustChainError(f"Connection error: {e}")

    async def health(self) -> Dict[str, Any]:
        """Check node health and status"""
        return await self._request("GET", "/health")

    async def get_miners(self) -> List[Dict[str, Any]]:
        """Get list of active miners"""
        return await self._request("GET", "/api/miners")

    async def get_balance(self, address: str) -> float:
        """Get balance for an RTC address"""
        data = await self._request("GET", "/wallet/balance", params={"miner_id": address})
        return data.get("amount_rtc", 0.0)

    async def get_epoch(self) -> Dict[str, Any]:
        """Get current network epoch and slot information"""
        return await self._request("GET", "/epoch")

    async def check_eligibility(self, address: str) -> Dict[str, Any]:
        """Check lottery eligibility for a miner"""
        return await self._request("GET", "/lottery/eligibility", params={"miner_id": address})

    async def submit_attestation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit hardware attestation / PoA proof"""
        return await self._request("POST", "/attest/submit", data=payload)

    async def transfer(self, from_address: str, to_address: str, amount: float, private_key_hex: str, memo: str = "") -> Dict[str, Any]:
        """
        Sign and execute a transfer of RTC.
        Requires `nacl` library for Ed25519 signing.
        """
        try:
            from nacl.signing import SigningKey
            import binascii
        except ImportError:
            raise RustChainError("Transfer requires 'pynacl' library. Install with: pip install pynacl")

        nonce = int(time.time() * 1000)
        
        # Prepare transaction data for signing
        tx_data = {
            "from": from_address,
            "to": to_address,
            "amount": amount,
            "memo": memo,
            "nonce": nonce
        }
        
        # Consistent serialization
        message = json.dumps(tx_data, sort_keys=True, separators=(",", ":")).encode()
        
        # Sign with Ed25519
        try:
            sk = SigningKey(binascii.unhexlify(private_key_hex))
            signature = sk.sign(message).signature
            public_key = sk.verify_key.encode()
            
            payload = {
                "from_address": from_address,
                "to_address": to_address,
                "amount_rtc": amount,
                "nonce": nonce,
                "signature": binascii.hexlify(signature).decode(),
                "public_key": binascii.hexlify(public_key).decode(),
                "memo": memo
            }
            
            return await self._request("POST", "/wallet/transfer/signed", data=payload)
        except Exception as e:
            raise RustChainError(f"Signing failed: {e}")
