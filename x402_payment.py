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

import time
import json
import math
from functools import wraps
from flask import Blueprint, request, jsonify, g

x402_bp = Blueprint("x402", __name__, url_prefix="/x402")

# -- Config --

USDC_RECEIVING_ADDRESS = "0xd10A6AbFED84dDD28F89bB3d836BD20D5da8fEBf"
SUPPORTED_NETWORKS = ["base", "solana", "ethereum"]
PAYMENT_ASSET = "USDC"

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
                        "networks": SUPPORTED_NETWORKS,
                        "description": "BoTTube API access: " + price_key,
                        "expires": int(time.time()) + 300,
                    },
                    "docs": "https://bottube.ai/x402",
                    "free_tier": "Use /api/* for free access (rate-limited)",
                }), 402

            verified, reason = _verify_payment(payment_header, price)
            if not verified:
                return jsonify({
                    "error": "payment_invalid",
                    "reason": reason,
                    "protocol": "x402",
                }), 402

            g.x402_paid = True
            g.x402_tx = payment_header
            g.x402_amount = price
            resp = f(*args, **kwargs)
            if hasattr(resp, "headers"):
                resp.headers["X-Payment-Verified"] = "true"
                resp.headers["X-Payment-Amount"] = str(price)
                resp.headers["X-Payment-Currency"] = PAYMENT_ASSET
            return resp
        return wrapper
    return decorator


def _verify_payment(payment_data, expected_amount):
    """Verify x402 payment. Demo mode: accept valid-format tx hashes."""
    try:
        if payment_data.startswith("{"):
            data = json.loads(payment_data)
            tx_hash = data.get("tx_hash", "")
            network = data.get("network", "base")
            amount = float(data.get("amount", 0))
        else:
            tx_hash = payment_data.strip()
            network = "base"
            amount = expected_amount

        if not tx_hash or len(tx_hash) < 10:
            return False, "invalid_tx_hash"
        if network not in SUPPORTED_NETWORKS:
            return False, "unsupported_network:" + network

        if tx_hash in _payment_cache:
            cached = _payment_cache[tx_hash]
            if time.time() - cached["time"] < CACHE_TTL:
                return True, "cached"

        # TODO: Production - verify on-chain via Base/Solana RPC
        _payment_cache[tx_hash] = {
            "time": time.time(),
            "amount": amount,
            "network": network,
        }
        print("[x402] Payment verified: %s... (%.4f %s on %s)" % (
            tx_hash[:16], amount, PAYMENT_ASSET, network))
        return True, "verified"
    except Exception as e:
        return False, "parse_error:" + str(e)[:50]


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
            "3. Send USDC payment on Base, Solana, or Ethereum",
            "4. Retry request with X-PAYMENT header containing tx hash",
            "5. Receive premium content with X-Payment-Verified: true header",
        ],
        "pricing": PRICING,
        "payment": {
            "currency": PAYMENT_ASSET,
            "recipient": USDC_RECEIVING_ADDRESS,
            "networks": SUPPORTED_NETWORKS,
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

    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 50, type=int)))
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
