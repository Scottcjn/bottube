#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RustChain Crypto Client
Ed25519 signing for RTC transactions
"""

import os
import hashlib
import base64
from typing import Tuple, Optional
from dataclasses import dataclass
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


@dataclass
class Wallet:
    """Represents an RTC wallet"""
    private_key: ed25519.Ed25519PrivateKey
    public_key: bytes
    address: str
    
    @classmethod
    def generate(cls) -> 'Wallet':
        """Generate a new wallet"""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        address = cls._public_key_to_address(public_key)
        
        return cls(
            private_key=private_key,
            public_key=public_key,
            address=address
        )
    
    @classmethod
    def from_private_key(cls, private_key_pem: bytes, password: bytes = None) -> 'Wallet':
        """Load wallet from PEM-encoded private key"""
        private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=password,
            backend=default_backend()
        )
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        address = cls._public_key_to_address(public_key)
        
        return cls(
            private_key=private_key,
            public_key=public_key,
            address=address
        )
    
    @staticmethod
    def _public_key_to_address(public_key: bytes) -> str:
        """Convert public key to wallet address"""
        # Hash public key
        hash1 = hashlib.sha256(public_key).digest()
        hash2 = hashlib.blake2b(hash1, digest_size=20).digest()
        
        # Format as Ethereum-style address
        return '0x' + hash2.hex()
    
    def sign(self, message: bytes) -> bytes:
        """Sign a message"""
        return self.private_key.sign(message)
    
    def get_public_key_pem(self) -> bytes:
        """Get public key in PEM format"""
        return self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
    
    def get_private_key_pem(self, password: bytes = None) -> bytes:
        """Get private key in PEM format"""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=(
                serialization.BestAvailableEncryption(password)
                if password else serialization.NoEncryption()
            )
        )


class RustChainCrypto:
    """Crypto utilities for RustChain"""
    
    def __init__(self, wallet: Optional[Wallet] = None):
        self.wallet = wallet
    
    def create_transfer(self, to_address: str, amount: float) -> dict:
        """Create a signed transfer"""
        if not self.wallet:
            raise ValueError("No wallet configured")
        
        # Create transfer message
        message = {
            'from': self.wallet.address,
            'to': to_address,
            'amount': amount,
            'timestamp': int(__import__('time').time()),
            'nonce': self._generate_nonce()
        }
        
        # Sign the message
        message_bytes = str(message).encode()
        signature = self.wallet.sign(message_bytes)
        
        return {
            'message': message,
            'signature': base64.b64encode(signature).decode(),
            'public_key': base64.b64encode(self.wallet.public_key).decode()
        }
    
    def _generate_nonce(self) -> str:
        """Generate a unique nonce"""
        return hashlib.sha256(
            f"{self.wallet.address}{__import__('time').time()}".encode()
        ).hexdigest()[:16]
    
    @staticmethod
    def verify_signature(message: dict, signature: str, public_key: str) -> bool:
        """Verify a signature"""
        try:
            pub_key_bytes = base64.b64decode(public_key)
            sig_bytes = base64.b64decode(signature)
            
            public_key_obj = ed25519.Ed25519PublicKey.from_public_bytes(pub_key_bytes)
            public_key_obj.verify(sig_bytes, str(message).encode())
            return True
        except:
            return False


def main():
    """Demo wallet generation"""
    print("=" * 60)
    print("RustChain Wallet Demo")
    print("=" * 60)
    
    # Generate new wallet
    print("\nGenerating new wallet...")
    wallet = Wallet.generate()
    
    print(f"Address: {wallet.address}")
    print(f"Public Key: {wallet.public_key.hex()[:40]}...")
    
    # Save wallet (in production, encrypt this!)
    print("\nSaving wallet to wallet.json...")
    with open('wallet.json', 'wb') as f:
        f.write(wallet.get_private_key_pem())
    print("Wallet saved!")
    
    # Create a demo transfer
    print("\nCreating demo transfer...")
    crypto = RustChainCrypto(wallet)
    transfer = crypto.create_transfer(
        to_address='0x1234567890abcdef1234567890abcdef12345678',
        amount=10.5
    )
    print(f"Transfer: {transfer['message']}")
    print(f"Signature: {transfer['signature'][:40]}...")
    
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()
