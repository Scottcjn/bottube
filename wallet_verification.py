# SPDX-License-Identifier: MIT
"""Cryptographic wallet proof-of-possession verification for BoTTube deposits.

Prevents self-asserted wallet binding attacks (#2265) where an attacker binds
a victim's public ETH/SOL/ERG address to their own account via
``POST /api/agents/me/wallet`` and harvests that victim's inbound treasury
transfers.

Dependencies are strictly limited to the Python standard library plus
``PyNaCl`` (already declared in ``requirements-ci.txt``):

- ``eth``: EIP-191 ``personal_sign`` using pure-Python Keccak-256 and
  secp256k1 public-key recovery with EIP-2 low-``s`` enforcement.
- ``sol``: Ed25519 signature verification via ``nacl.signing.VerifyKey`` against
  the canonical 32-byte Base58 Solana public key.
- ``erg``: secp256k1 ECDSA verification over ``blake2b256(message)`` against the
  33-byte compressed public key encoded in the Ergo mainnet P2PK address
  (``0x01 || pk33 || blake2b256(0x01 || pk33)[:4]``).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from typing import Any

import nacl.exceptions
import nacl.signing
from flask import jsonify

SUPPORTED_WALLET_CHAINS = frozenset({"eth", "sol", "erg"})
DEPOSIT_BINDING_FIELDS = ("eth", "sol", "erg")
CHALLENGE_TTL_SECONDS = 600

_CHAIN_LABELS = {
    "eth": "Ethereum",
    "sol": "Solana",
    "erg": "Ergo",
}

_ETH_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]+$")
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_INDEX = {ch: idx for idx, ch in enumerate(_BASE58_ALPHABET)}
_HEX_SIG_RE = re.compile(r"^(?:0x)?([0-9a-fA-F]{128}|[0-9a-fA-F]{130})$")

# Keccak-256 constants (Ethereum pre-NIST padding 0x01)
_KECCAK_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
_KECCAK_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)
_MASK64 = 0xFFFFFFFFFFFFFFFF

# secp256k1 parameters
_SECP256K1_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_SECP256K1_GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
_SECP256K1_GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
_SECP256K1_G = (_SECP256K1_GX, _SECP256K1_GY)


def _rol64(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (64 - shift))) & _MASK64 if shift else value


def _keccak_f1600(state: list[list[int]]) -> None:
    for rc in _KECCAK_RC:
        c = [state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol64(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol64(state[x][y], _KECCAK_ROT[x][y])
        for x in range(5):
            for y in range(5):
                state[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y])
        state[0][0] ^= rc


def keccak_256(data: bytes) -> bytes:
    """Compute Ethereum Keccak-256 digest using pure Python."""
    rate = 136
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != 0:
        padded.append(0x00)
    padded[-1] |= 0x80
    state = [[0] * 5 for _ in range(5)]
    for offset in range(0, len(padded), rate):
        block = padded[offset : offset + rate]
        for i in range(rate // 8):
            state[i % 5][i // 5] ^= int.from_bytes(block[i * 8 : (i + 1) * 8], "little")
        _keccak_f1600(state)
    out = bytearray()
    for i in range(4):
        out.extend(state[i % 5][i // 5].to_bytes(8, "little"))
    return bytes(out)


def _point_add(
    p1: tuple[int, int] | None,
    p2: tuple[int, int] | None,
) -> tuple[int, int] | None:
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % _SECP256K1_P == 0 or y1 % _SECP256K1_P == 0:
            return None
        lam = (3 * x1 * x1 * pow((2 * y1) % _SECP256K1_P, -1, _SECP256K1_P)) % _SECP256K1_P
    else:
        lam = ((y2 - y1) * pow((x2 - x1) % _SECP256K1_P, -1, _SECP256K1_P)) % _SECP256K1_P
    x3 = (lam * lam - x1 - x2) % _SECP256K1_P
    y3 = (lam * (x1 - x3) - y1) % _SECP256K1_P
    return (x3, y3)


def _point_mul(scalar: int, point: tuple[int, int] | None) -> tuple[int, int] | None:
    if point is None:
        return None
    k = scalar % _SECP256K1_N
    if k == 0:
        return None
    res = None
    addend: tuple[int, int] | None = point
    while k:
        if k & 1:
            res = _point_add(res, addend)
        addend = _point_add(addend, addend)
        k >>= 1
    return res


def _decompress_secp256k1_y(x: int, is_odd: bool) -> int | None:
    if x <= 0 or x >= _SECP256K1_P:
        return None
    y2 = (pow(x, 3, _SECP256K1_P) + 7) % _SECP256K1_P
    y = pow(y2, (_SECP256K1_P + 1) // 4, _SECP256K1_P)
    if (y * y) % _SECP256K1_P != y2:
        return None
    if bool(y & 1) != is_odd:
        y = _SECP256K1_P - y
    return y


def _decompress_secp256k1_pubkey(pk33: bytes) -> tuple[int, int] | None:
    if len(pk33) != 33 or pk33[0] not in (0x02, 0x03):
        return None
    x = int.from_bytes(pk33[1:], "big")
    y = _decompress_secp256k1_y(x, pk33[0] == 0x03)
    return (x, y) if y is not None else None


def _compress_secp256k1_pubkey(point: tuple[int, int]) -> bytes:
    x, y = point
    prefix = b"\x03" if (y & 1) else b"\x02"
    return prefix + x.to_bytes(32, "big")


def _ecrecover_point(digest32: bytes, sig65: bytes) -> tuple[int, int] | None:
    if len(digest32) != 32 or len(sig65) != 65:
        return None
    r = int.from_bytes(sig65[:32], "big")
    s = int.from_bytes(sig65[32:64], "big")
    v = sig65[64]
    if v in (27, 28):
        rec_id = v - 27
    elif v in (0, 1):
        rec_id = v
    else:
        return None
    # Enforce canonical low-s (EIP-2) to eliminate signature malleability.
    if not (1 <= r < _SECP256K1_N and 1 <= s <= _SECP256K1_N // 2):
        return None
    ry = _decompress_secp256k1_y(r, bool(rec_id & 1))
    if ry is None:
        return None
    r_point = (r, ry)
    z = int.from_bytes(digest32, "big") % _SECP256K1_N
    r_inv = pow(r, -1, _SECP256K1_N)
    s_r = _point_mul(s, r_point)
    neg_g = (_SECP256K1_GX, (_SECP256K1_P - _SECP256K1_GY) % _SECP256K1_P)
    neg_z_g = _point_mul(z, neg_g) if z else None
    return _point_mul(r_inv, _point_add(s_r, neg_z_g))


def decode_base58(value: str) -> bytes:
    """Decode strict Base58 string preserving leading zero bytes."""
    if not value or not _BASE58_RE.match(value):
        raise ValueError("Invalid Base58 string")
    num = 0
    for ch in value:
        num = num * 58 + _BASE58_INDEX[ch]
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    leading_zeros = 0
    for ch in value:
        if ch == "1":
            leading_zeros += 1
        else:
            break
    return (b"\x00" * leading_zeros) + raw


def normalize_wallet_address(chain: str, address: str) -> str:
    """Validate and normalize a wallet address for a deposit-binding chain."""
    if not isinstance(chain, str) or chain not in SUPPORTED_WALLET_CHAINS:
        raise ValueError("Unsupported chain (allowed: eth, sol, erg)")
    if not isinstance(address, str):
        raise TypeError("address must be a string")
    cleaned = address.strip()
    if not cleaned:
        raise ValueError("address is required")

    if chain == "eth":
        if not _ETH_ADDR_RE.match(cleaned):
            raise ValueError("Invalid Ethereum address format (expected 0x + 40 hex chars)")
        return cleaned.lower()

    if chain == "sol":
        if not (32 <= len(cleaned) <= 44) or not _BASE58_RE.match(cleaned):
            raise ValueError("Invalid Solana address format")
        pubkey = decode_base58(cleaned)
        if len(pubkey) != 32:
            raise ValueError("Invalid Solana public key length (expected 32 bytes)")
        return cleaned

    # chain == "erg" (mainnet P2PK: 0x01 || 33-byte compressed secp256k1 pubkey || 4-byte blake2b256 checksum)
    if not cleaned.startswith("9"):
        raise ValueError("Invalid Ergo mainnet P2PK address")
    raw = decode_base58(cleaned)
    if len(raw) != 38 or raw[0] != 0x01:
        raise ValueError("Invalid Ergo mainnet P2PK address encoding")
    checksum = hashlib.blake2b(raw[:34], digest_size=32).digest()[:4]
    if not hmac.compare_digest(checksum, raw[34:38]):
        raise ValueError("Invalid Ergo address checksum")
    if _decompress_secp256k1_pubkey(raw[1:34]) is None:
        raise ValueError("Invalid Ergo public key")
    return cleaned


def _decode_hex_signature(signature: str, expected_bytes: int) -> bytes | None:
    if not isinstance(signature, str):
        return None
    cleaned = signature.strip()
    if not _HEX_SIG_RE.match(cleaned):
        return None
    hex_body = cleaned[2:] if cleaned.startswith(("0x", "0X")) else cleaned
    if len(hex_body) != expected_bytes * 2:
        return None
    try:
        return bytes.fromhex(hex_body)
    except ValueError:
        return None


def verify_wallet_signature(chain: str, address: str, message: str, signature: str) -> bool:
    """Verify cryptographic proof of possession for ``address`` over ``message``."""
    try:
        norm_addr = normalize_wallet_address(chain, address)
    except (TypeError, ValueError):
        return False
    if not isinstance(message, str) or not message or not isinstance(signature, str):
        return False
    msg_bytes = message.encode("utf-8")

    if chain == "eth":
        sig_bytes = _decode_hex_signature(signature, 65)
        if sig_bytes is None:
            return False
        prefixed = b"\x19Ethereum Signed Message:\n" + str(len(msg_bytes)).encode("ascii") + msg_bytes
        digest = keccak_256(prefixed)
        point = _ecrecover_point(digest, sig_bytes)
        if point is None:
            return False
        pub_uncompressed = point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big")
        recovered = "0x" + keccak_256(pub_uncompressed)[-20:].hex()
        return hmac.compare_digest(recovered, norm_addr)

    if chain == "sol":
        try:
            pubkey32 = decode_base58(norm_addr)
        except ValueError:
            return False
        sig_bytes = _decode_hex_signature(signature, 64)
        if sig_bytes is None:
            try:
                sig_bytes = decode_base58(signature.strip())
            except ValueError:
                return False
        if len(sig_bytes) != 64:
            return False
        try:
            nacl.signing.VerifyKey(pubkey32).verify(msg_bytes, sig_bytes)
            return True
        except (nacl.exceptions.BadSignatureError, nacl.exceptions.CryptoError, ValueError):
            return False

    # chain == "erg"
    sig_bytes = _decode_hex_signature(signature, 65)
    if sig_bytes is None:
        return False
    raw = decode_base58(norm_addr)
    pk33 = raw[1:34]
    digest = hashlib.blake2b(msg_bytes, digest_size=32).digest()
    point = _ecrecover_point(digest, sig_bytes)
    if point is None:
        return False
    return hmac.compare_digest(_compress_secp256k1_pubkey(point), pk33)


def _ensure_tables_in_tx(db: sqlite3.Connection) -> None:
    """Create verification tables with plain DDL statements (no implicit commits)."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS wallet_verification_challenges (
            challenge_id TEXT PRIMARY KEY,
            agent_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,
            chain TEXT NOT NULL,
            address TEXT NOT NULL,
            message TEXT NOT NULL,
            nonce TEXT NOT NULL,
            expires_at REAL NOT NULL,
            used_at REAL DEFAULT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_wallet_challenges_agent "
        "ON wallet_verification_challenges(agent_id, created_at DESC)"
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS verified_wallets (
            chain TEXT NOT NULL,
            address TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,
            verified_at REAL NOT NULL,
            challenge_id TEXT NOT NULL,
            PRIMARY KEY (chain, address),
            UNIQUE (agent_id, chain)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_verified_wallets_agent_chain "
        "ON verified_wallets(agent_id, chain)"
    )


def init_wallet_verification_tables(db: sqlite3.Connection) -> None:
    """Create challenge and verified-ownership tables idempotently."""
    _ensure_tables_in_tx(db)
    db.commit()


def _build_challenge_message(
    *,
    chain: str,
    address: str,
    agent_id: int,
    agent_name: str,
    nonce: str,
    challenge_id: str,
    issued_at: float,
    expires_at: float,
) -> str:
    return (
        "BoTTube Wallet Ownership Verification\n"
        "Domain: bottube.ai\n"
        f"Chain: {chain}\n"
        f"Address: {address}\n"
        f"Agent: {agent_name}\n"
        f"Agent-ID: {int(agent_id)}\n"
        f"Nonce: {nonce}\n"
        f"Challenge-ID: {challenge_id}\n"
        f"Issued-At: {int(issued_at)}\n"
        f"Expires-At: {int(expires_at)}"
    )


def create_wallet_challenge(
    db: sqlite3.Connection,
    *,
    agent_id: int,
    agent_name: str,
    chain: str,
    address: str,
    ttl_seconds: int = CHALLENGE_TTL_SECONDS,
    now: float | None = None,
) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], int] | None]:
    """Issue a single-use short-TTL challenge bound to agent, chain, and normalized address."""
    try:
        norm_addr = normalize_wallet_address(chain, address)
    except (TypeError, ValueError) as exc:
        return None, ({"error": str(exc), "code": "INVALID_WALLET_ADDRESS"}, 400)

    init_wallet_verification_tables(db)
    existing = db.execute(
        "SELECT agent_id FROM verified_wallets WHERE chain = ? AND address = ?",
        (chain, norm_addr),
    ).fetchone()
    if existing and int(existing["agent_id"]) != int(agent_id):
        return None, (
            {
                "error": "Wallet address is already verified by another account",
                "code": "WALLET_ALREADY_CLAIMED",
            },
            409,
        )

    issued_at = float(time.time() if now is None else now)
    expires_at = issued_at + float(ttl_seconds)
    challenge_id = secrets.token_hex(16)
    nonce = secrets.token_hex(16)
    message = _build_challenge_message(
        chain=chain,
        address=norm_addr,
        agent_id=int(agent_id),
        agent_name=agent_name,
        nonce=nonce,
        challenge_id=challenge_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    db.execute(
        """
        INSERT INTO wallet_verification_challenges
            (challenge_id, agent_id, agent_name, chain, address, message, nonce, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (challenge_id, int(agent_id), agent_name, chain, norm_addr, message, nonce, expires_at, issued_at),
    )
    db.commit()
    return {
        "ok": True,
        "challenge_id": challenge_id,
        "chain": chain,
        "address": norm_addr,
        "nonce": nonce,
        "message": message,
        "expires_at": expires_at,
    }, None


def _update_agent_wallet_column(
    db: sqlite3.Connection, *, agent_id: int, chain: str, address: str
) -> None:
    if chain == "eth":
        db.execute("UPDATE agents SET eth_address = ? WHERE id = ?", (address, agent_id))
    elif chain == "sol":
        db.execute("UPDATE agents SET sol_address = ? WHERE id = ?", (address, agent_id))
    elif chain == "erg":
        db.execute("UPDATE agents SET erg_address = ? WHERE id = ?", (address, agent_id))
    else:
        raise ValueError("Unsupported chain")


def verify_wallet_challenge(
    db: sqlite3.Connection,
    *,
    agent_id: int,
    agent_name: str,
    challenge_id: str,
    signature: str,
    now: float | None = None,
) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], int] | None]:
    """Verify a signed wallet challenge, consume it atomically, and bind verified ownership."""
    init_wallet_verification_tables(db)
    row = db.execute(
        """
        SELECT challenge_id, agent_id, agent_name, chain, address, message, expires_at, used_at
        FROM wallet_verification_challenges
        WHERE challenge_id = ?
        """,
        (challenge_id,),
    ).fetchone()
    if not row:
        return None, ({"error": "Challenge not found", "code": "CHALLENGE_NOT_FOUND"}, 404)
    if int(row["agent_id"]) != int(agent_id):
        return None, ({"error": "Challenge does not belong to this agent", "code": "CHALLENGE_FORBIDDEN"}, 403)
    if row["used_at"] is not None:
        return None, ({"error": "Challenge has already been used", "code": "CHALLENGE_ALREADY_USED"}, 409)

    now_ts = float(time.time() if now is None else now)
    if now_ts > float(row["expires_at"]):
        return None, ({"error": "Challenge has expired", "code": "CHALLENGE_EXPIRED"}, 400)

    chain = str(row["chain"])
    address = str(row["address"])
    message = str(row["message"])
    if not verify_wallet_signature(chain, address, message, signature):
        return None, ({"error": "Invalid cryptographic wallet signature", "code": "INVALID_WALLET_SIGNATURE"}, 403)

    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
    try:
        consume_cur = db.execute(
            """
            UPDATE wallet_verification_challenges
            SET used_at = ?
            WHERE challenge_id = ? AND agent_id = ? AND used_at IS NULL AND expires_at >= ?
            """,
            (now_ts, challenge_id, int(agent_id), now_ts),
        )
        if consume_cur.rowcount != 1:
            db.rollback()
            return None, (
                {"error": "Challenge has already been used or expired", "code": "CHALLENGE_ALREADY_USED"},
                409,
            )

        existing = db.execute(
            "SELECT agent_id FROM verified_wallets WHERE chain = ? AND address = ?",
            (chain, address),
        ).fetchone()
        if existing and int(existing["agent_id"]) != int(agent_id):
            db.rollback()
            return None, (
                {
                    "error": "Wallet address is already verified by another account",
                    "code": "WALLET_ALREADY_CLAIMED",
                },
                409,
            )

        db.execute(
            "DELETE FROM verified_wallets WHERE agent_id = ? AND chain = ? AND address != ?",
            (int(agent_id), chain, address),
        )
        db.execute(
            """
            INSERT INTO verified_wallets (chain, address, agent_id, agent_name, verified_at, challenge_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chain, address) DO UPDATE SET
                agent_name = excluded.agent_name,
                verified_at = excluded.verified_at,
                challenge_id = excluded.challenge_id
            WHERE verified_wallets.agent_id = excluded.agent_id
            """,
            (chain, address, int(agent_id), agent_name, now_ts, challenge_id),
        )
        _update_agent_wallet_column(db, agent_id=int(agent_id), chain=chain, address=address)
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return None, (
            {
                "error": "Wallet address is already verified by another account",
                "code": "WALLET_ALREADY_CLAIMED",
            },
            409,
        )

    return {
        "ok": True,
        "verified": True,
        "chain": chain,
        "address": address,
        "verified_at": now_ts,
    }, None


def clear_verified_wallet(db: sqlite3.Connection, *, agent_id: int, chain: str) -> None:
    """Remove verified wallet ownership when an agent clears their bound address."""
    if chain not in SUPPORTED_WALLET_CHAINS:
        return
    _ensure_tables_in_tx(db)
    db.execute(
        "DELETE FROM verified_wallets WHERE agent_id = ? AND chain = ?",
        (int(agent_id), chain),
    )


def get_verified_wallet_flags(
    db: sqlite3.Connection,
    *,
    agent_id: int,
    current_wallets: dict[str, str] | None = None,
) -> dict[str, bool]:
    """Return per-chain verification flags matching current bound addresses."""
    flags = {chain: False for chain in DEPOSIT_BINDING_FIELDS}
    try:
        rows = db.execute(
            "SELECT chain, address FROM verified_wallets WHERE agent_id = ?",
            (int(agent_id),),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return flags
        raise
    for row in rows:
        chain = row["chain"]
        if chain not in flags:
            continue
        verified_addr = str(row["address"] or "")
        if not verified_addr:
            continue
        if current_wallets is not None:
            raw_cur = (current_wallets.get(chain) or "").strip()
            try:
                norm_cur = normalize_wallet_address(chain, raw_cur)
            except ValueError:
                norm_cur = ""
            flags[chain] = hmac.compare_digest(norm_cur, verified_addr)
        else:
            flags[chain] = True
    return flags


def is_wallet_verified(
    db: sqlite3.Connection,
    *,
    chain: str,
    address: str,
    agent_id: int | None = None,
    agent_name: str | None = None,
) -> bool:
    """Return True only when ``address`` has verified proof of possession for this agent."""
    try:
        norm_addr = normalize_wallet_address(chain, address)
    except ValueError:
        return False

    try:
        row = db.execute(
            "SELECT agent_id, agent_name FROM verified_wallets WHERE chain = ? AND address = ?",
            (chain, norm_addr),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return False
        raise
    if not row:
        return False
    if agent_id is not None and int(row["agent_id"]) != int(agent_id):
        return False
    if agent_name is not None and row["agent_name"] != agent_name:
        return False
    return agent_id is not None or agent_name is not None


def require_verified_deposit_wallet(
    db: sqlite3.Connection,
    *,
    chain: str,
    address: str,
    agent_id: int | None = None,
    agent_name: str | None = None,
):
    """Return None if verified, or a 403 Flask error response tuple for unverified claims."""
    if is_wallet_verified(
        db,
        chain=chain,
        address=address,
        agent_id=agent_id,
        agent_name=agent_name,
    ):
        return None
    label = _CHAIN_LABELS.get(chain, chain.upper())
    return (
        jsonify(
            {
                "error": (
                    f"{label} wallet has not passed cryptographic ownership verification. "
                    "Complete POST /api/agents/me/wallet/challenge and "
                    "POST /api/agents/me/wallet/verify first."
                ),
                "code": "WALLET_NOT_VERIFIED",
                "chain": chain,
            }
        ),
        403,
    )
