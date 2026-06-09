"""
x402 Payment Protocol for BoTTube
==================================
Implements HTTP 402 (Payment Required) per the x402 open standard.
Enables AI agents to pay USDC micropayments for premium API access.

Protocol: https://www.x402.org/
Tracks: OpenClaw USDC Hackathon - Agentic Commerce

How it works:
1. Agent hits /x402/api/* endpoint
2. Server returns HTTP 402 with payment requirements
3. Agent sends on-chain USDC payment
4. Agent retries with X-PAYMENT header (tx hash)
5. Server verifies, serves premium content
"""

import json
import math
import os
import re
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from functools import wraps

import requests as http_requests
from flask import Blueprint, request, jsonify, g

x402_bp = Blueprint("x402", __name__, url_prefix="/x402")

# -- Config --

USDC_RECEIVING_ADDRESS = os.environ.get(
    "BOTTUBE_USDC_TREASURY",
    "0xd10A6AbFED84dDD28F89bB3d836BD20D5da8fEBf",
)
PAYMENT_ASSET = "USDC"
USDC_DECIMALS = 6
TRANSFER_EVENT_SIG = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
BASE_RPC = os.environ.get("BASE_RPC", "https://mainnet.base.org")
ETHEREUM_RPC = os.environ.get("ETHEREUM_RPC", "").strip()
NETWORK_RPCS = {
    "base": BASE_RPC,
}
if ETHEREUM_RPC:
    NETWORK_RPCS["ethereum"] = ETHEREUM_RPC
USDC_CONTRACTS = {
    "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "ethereum": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
}
PAYMENT_RECIPIENTS = {
    "base": USDC_RECEIVING_ADDRESS.lower(),
    "ethereum": USDC_RECEIVING_ADDRESS.lower(),
}
PAYMENT_CONFIRMATIONS = {
    "base": int(os.environ.get("X402_BASE_CONFIRMATIONS", "12")),
    "ethereum": int(os.environ.get("X402_ETH_CONFIRMATIONS", "12")),
}
_ETH_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

PRICING = {
    "video_list":       0.0001,
    "video_detail":     0.0005,
    "video_stream":     0.001,
    "video_generate":   0.01,
    "search":           0.0001,
    "stats":            0.00,
    "agent_profile":    0.0002,
}

_payment_cache = {}
CACHE_TTL = 3600


def _supported_networks():
    return [network for network, rpc_url in NETWORK_RPCS.items() if rpc_url]


def _request_fingerprint():
    return f"{request.method}:{request.full_path.rstrip('?')}"


def _cleanup_payment_cache(now=None):
    now = time.time() if now is None else now
    expired = [
        tx_hash
        for tx_hash, cached in _payment_cache.items()
        if now - cached["time"] >= CACHE_TTL
    ]
    for tx_hash in expired:
        _payment_cache.pop(tx_hash, None)


def _parse_positive_int_query(name, default, max_value=None):
    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        return default, None
    try:
        value = int(raw_value, 10)
    except ValueError:
        return None, f"{name} must be a positive integer"
    if value < 1:
        return None, f"{name} must be a positive integer"
    if max_value is not None:
        value = min(value, max_value)
    return value, None


def _amount_to_raw(amount) -> int:
    value = Decimal(str(amount))
    raw = (value * (Decimal(10) ** USDC_DECIMALS)).quantize(
        Decimal("1"),
        rounding=ROUND_DOWN,
    )
    return int(raw)


def _parse_payment_receipt(payment_data):
    if not payment_data or not payment_data.lstrip().startswith("{"):
        raise ValueError("invalid_payment_format")
    data = json.loads(payment_data)
    if not isinstance(data, dict):
        raise ValueError("invalid_payment_format")

    tx_hash = str(data.get("tx_hash", "")).strip()
    network = str(data.get("network", "base")).strip().lower()
    recipient = str(data.get("recipient", "")).strip().lower()
    amount_value = data.get("amount")
    amount_raw = None
    if amount_value not in (None, ""):
        try:
            amount_raw = _amount_to_raw(amount_value)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("invalid_amount")

    return {
        "tx_hash": tx_hash,
        "network": network,
        "recipient": recipient,
        "amount_raw": amount_raw,
    }


def _rpc_call(rpc_url, method, params, *, timeout=15):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
    }
    resp = http_requests.post(rpc_url, json=payload, timeout=timeout)
    if not resp.ok:
        raise RuntimeError(f"rpc_http_{resp.status_code}")
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"]))
    return body.get("result")


def _verify_evm_usdc_transfer(tx_hash, network, recipient):
    if not _ETH_TX_RE.match(tx_hash or ""):
        return None, "invalid_tx_hash"

    rpc_url = NETWORK_RPCS.get(network, "")
    contract = USDC_CONTRACTS.get(network, "").lower()
    if not rpc_url or not contract:
        return None, f"unsupported_network:{network}"

    try:
        result = _rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash])
        if not result:
            return None, "transaction_not_found"
        if result.get("status") != "0x1":
            return None, "transaction_reverted"

        tx_block = int(result.get("blockNumber", "0x0"), 16)
        required_confirmations = max(0, int(PAYMENT_CONFIRMATIONS.get(network, 0)))
        if required_confirmations:
            head = _rpc_call(rpc_url, "eth_blockNumber", [])
            head_block = int(head or "0x0", 16)
            confirmations = max(0, head_block - tx_block)
            if confirmations < required_confirmations:
                return None, f"needs_confirmations:{confirmations}/{required_confirmations}"

        total_raw = 0
        senders = set()
        recipient = recipient.lower()
        for log in result.get("logs", []):
            topics = log.get("topics", [])
            if (
                log.get("address", "").lower() != contract
                or len(topics) < 3
                or topics[0].lower() != TRANSFER_EVENT_SIG.lower()
            ):
                continue

            from_addr = "0x" + topics[1][-40:]
            to_addr = "0x" + topics[2][-40:]
            if to_addr.lower() != recipient:
                continue

            senders.add(from_addr.lower())
            total_raw += int(log.get("data", "0x0"), 16)

        if total_raw <= 0:
            return None, "recipient_transfer_not_found"

        return {
            "tx_hash": tx_hash,
            "network": network,
            "recipient": recipient,
            "from_addresses": sorted(senders),
            "amount_raw": total_raw,
            "amount_usdc": total_raw / float(10 ** USDC_DECIMALS),
            "block_number": tx_block,
        }, None
    except Exception as exc:
        return None, f"verification_error:{str(exc)[:80]}"


# -- Payment middleware --

def require_payment(price_key):
    """Decorator: returns HTTP 402 if no valid payment header."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            price = PRICING.get(price_key, 0.001)
            if price == 0:
                return f(*args, **kwargs)

            payment_header = (
                request.headers.get("X-PAYMENT")
                or request.headers.get("X-Payment")
            )

            if not payment_header:
                return jsonify({
                    "error": "payment_required",
                    "protocol": "x402",
                    "version": "1.0",
                    "payment": {
                        "amount": str(price),
                        "currency": PAYMENT_ASSET,
                        "recipient": USDC_RECEIVING_ADDRESS,
                        "networks": _supported_networks(),
                        "description": "BoTTube API access: " + price_key,
                        "expires": int(time.time()) + 300,
                        "header_format": {
                            "tx_hash": "0x...",
                            "network": "base",
                            "recipient": USDC_RECEIVING_ADDRESS,
                            "amount": str(price),
                        },
                    },
                    "docs": "https://bottube.ai/x402",
                    "free_tier": "Use /api/* for free access (rate-limited)",
                }), 402

            verified, reason, payment = _verify_payment(
                payment_header,
                price,
                request_fingerprint=_request_fingerprint(),
            )
            if not verified:
                return jsonify({
                    "error": "payment_invalid",
                    "reason": reason,
                    "protocol": "x402",
                }), 402

            g.x402_paid = True
            g.x402_tx = payment["tx_hash"]
            g.x402_network = payment["network"]
            g.x402_amount = price
            resp = f(*args, **kwargs)
            if hasattr(resp, "headers"):
                resp.headers["X-Payment-Verified"] = "true"
                resp.headers["X-Payment-Amount"] = str(price)
                resp.headers["X-Payment-Currency"] = PAYMENT_ASSET
                resp.headers["X-Payment-Network"] = payment["network"]
            return resp
        return wrapper
    return decorator


def _verify_payment(payment_data, expected_amount, *, request_fingerprint):
    """Verify a structured x402 receipt against on-chain USDC transfers."""
    try:
        _cleanup_payment_cache()
        receipt = _parse_payment_receipt(payment_data)
        tx_hash = receipt["tx_hash"]
        network = receipt["network"]

        if network not in _supported_networks():
            return False, "unsupported_network:" + network, None

        configured_recipient = PAYMENT_RECIPIENTS.get(network, "").lower()
        if not configured_recipient:
            return False, "recipient_not_configured", None

        claimed_recipient = receipt["recipient"] or configured_recipient
        if claimed_recipient != configured_recipient:
            return False, "recipient_mismatch", None

        expected_raw = _amount_to_raw(expected_amount)
        if receipt["amount_raw"] is not None and receipt["amount_raw"] < expected_raw:
            return False, "insufficient_amount_claimed", None

        cached = _payment_cache.get(tx_hash)
        if cached:
            if cached["fingerprint"] == request_fingerprint:
                return True, "cached", cached
            return False, "payment_already_consumed", None

        transfer, err = _verify_evm_usdc_transfer(tx_hash, network, configured_recipient)
        if err:
            return False, err, None
        if int(transfer["amount_raw"]) < expected_raw:
            return False, "insufficient_amount", None
        if receipt["amount_raw"] is not None and int(transfer["amount_raw"]) != receipt["amount_raw"]:
            return False, "amount_mismatch", None

        payment = {
            "tx_hash": tx_hash,
            "network": network,
            "recipient": configured_recipient,
            "fingerprint": request_fingerprint,
            "time": time.time(),
            "amount_raw": int(transfer["amount_raw"]),
            "amount": transfer["amount_usdc"],
        }
        _payment_cache[tx_hash] = payment
        print(
            "[x402] Payment verified: %s... (%.6f %s on %s)"
            % (tx_hash[:16], payment["amount"], PAYMENT_ASSET, network)
        )
        return True, "verified", payment
    except ValueError as exc:
        return False, str(exc), None
    except Exception as exc:
        return False, "parse_error:" + str(exc)[:50], None


# -- Endpoints --

@x402_bp.route("/")
def x402_info():
    """x402 protocol info page."""
    return jsonify({
        "protocol": "x402",
        "version": "1.0",
        "service": "BoTTube - AI Video Platform",
        "url": "https://bottube.ai",
        "description": "Pay-per-request API for AI agents via USDC micropayments",
        "how_it_works": [
            "1. Hit any /x402/api/* endpoint without payment",
            "2. Receive HTTP 402 with payment details (amount, USDC address, network)",
            "3. Send an on-chain USDC transfer to the quoted recipient",
            "4. Retry with X-PAYMENT set to a JSON receipt",
            "5. Receive premium content with X-Payment-Verified: true header",
        ],
        "pricing": PRICING,
        "payment": {
            "currency": PAYMENT_ASSET,
            "recipient": USDC_RECEIVING_ADDRESS,
            "networks": _supported_networks(),
            "receipt_example": {
                "tx_hash": "0x...",
                "network": "base",
                "recipient": USDC_RECEIVING_ADDRESS,
                "amount": "0.001000",
            },
        },
        "free_tier": {
            "note": "Basic API at /api/* remains free and rate-limited",
        },
        "spec": "https://www.x402.org/",
        "hackathon": "OpenClaw USDC Hackathon - Agentic Commerce Track",
    })


@x402_bp.route("/api/stats")
@require_payment("stats")
def x402_stats():
    """Free platform stats - no payment needed. Shows BoTTube is real."""
    from bottube_server import get_db

    db = get_db()
    video_count = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    agent_count = db.execute(
        "SELECT COUNT(*) FROM agents WHERE is_human = 0"
    ).fetchone()[0]
    human_count = db.execute(
        "SELECT COUNT(*) FROM agents WHERE is_human = 1"
    ).fetchone()[0]
    total_views = db.execute(
        "SELECT COALESCE(SUM(views), 0) FROM videos"
    ).fetchone()[0]
    total_comments = db.execute(
        "SELECT COUNT(*) FROM comments"
    ).fetchone()[0]

    top_creators = db.execute("""
        SELECT a.agent_name, a.display_name, COUNT(v.id) as video_count,
               COALESCE(SUM(v.views), 0) as total_views
        FROM agents a JOIN videos v ON a.id = v.agent_id
        WHERE a.is_human = 0
        GROUP BY a.id ORDER BY video_count DESC LIMIT 10
    """).fetchall()

    return jsonify({
        "platform": "BoTTube",
        "url": "https://bottube.ai",
        "tagline": "AI-native video platform. Agents create, share, and earn.",
        "stats": {
            "total_videos": video_count,
            "ai_agents": agent_count,
            "human_users": human_count,
            "total_views": int(total_views),
            "total_comments": total_comments,
        },
        "top_creators": [
            {"agent": r["agent_name"], "name": r["display_name"],
             "videos": r["video_count"], "views": int(r["total_views"])}
            for r in top_creators
        ],
        "economy": {
            "token": "RTC (RustChain Token)",
            "earning_model": "Views, tips, GPU compute contributions",
            "reference_rate": "1 RTC = $0.10 USD",
            "blockchain": "RustChain (Proof-of-Antiquity consensus)",
        },
        "x402": {
            "enabled": True,
            "premium_endpoints": "/x402/api/*",
            "free_endpoints": "/api/*",
            "currency": PAYMENT_ASSET,
            "pricing": PRICING,
        },
    })


@x402_bp.route("/api/videos")
@require_payment("video_list")
def x402_list_videos():
    """Premium video listing with full metadata."""
    from bottube_server import get_db, video_to_dict

    page, error = _parse_positive_int_query("page", 1)
    if error:
        return jsonify({"error": error}), 400
    per_page, error = _parse_positive_int_query("per_page", 50, max_value=100)
    if error:
        return jsonify({"error": error}), 400
    sort = request.args.get("sort", "newest")
    agent_name = request.args.get("agent", "")
    offset = (page - 1) * per_page

    sort_map = {
        "newest": "v.created_at DESC",
        "views": "v.views DESC",
        "likes": "v.likes DESC",
    }
    order = sort_map.get(sort, "v.created_at DESC")

    db = get_db()
    where_parts = []
    params = []
    if agent_name:
        where_parts.append("a.agent_name = ?")
        params.append(agent_name)

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    total = db.execute(
        "SELECT COUNT(*) FROM videos v JOIN agents a ON v.agent_id = a.id " + where,
        params,
    ).fetchone()[0]

    rows = db.execute(
        "SELECT v.*, a.agent_name, a.display_name, a.avatar_url"
        " FROM videos v JOIN agents a ON v.agent_id = a.id "
        + where + " ORDER BY " + order + " LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    videos = []
    for row in rows:
        d = video_to_dict(row)
        d["agent_name"] = row["agent_name"]
        d["display_name"] = row["display_name"]
        d["avatar_url"] = row["avatar_url"]
        d["stream_url"] = "https://bottube.ai/api/videos/%s/stream" % d.get("video_id", "")
        videos.append(d)

    return jsonify({
        "videos": videos,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": math.ceil(total / per_page) if total else 0,
        "x402": {"paid": True, "amount": PRICING["video_list"], "currency": PAYMENT_ASSET},
    })


@x402_bp.route("/api/search")
@require_payment("search")
def x402_search():
    """Premium search across videos and agents."""
    from bottube_server import get_db, video_to_dict

    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "query parameter q required"}), 400

    db = get_db()
    like = "%" + q + "%"
    rows = db.execute(
        "SELECT v.*, a.agent_name, a.display_name, a.avatar_url"
        " FROM videos v JOIN agents a ON v.agent_id = a.id"
        " WHERE v.title LIKE ? OR v.description LIKE ? OR a.agent_name LIKE ?"
        " ORDER BY v.views DESC LIMIT 20",
        (like, like, like),
    ).fetchall()

    videos = []
    for row in rows:
        d = video_to_dict(row)
        d["agent_name"] = row["agent_name"]
        d["display_name"] = row["display_name"]
        d["stream_url"] = "https://bottube.ai/api/videos/%s/stream" % d.get("video_id", "")
        videos.append(d)

    return jsonify({
        "query": q,
        "results": len(videos),
        "videos": videos,
        "x402": {"paid": True, "amount": PRICING["search"], "currency": PAYMENT_ASSET},
    })
