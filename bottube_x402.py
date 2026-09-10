# SPDX-License-Identifier: MIT
"""BoTTube x402 Integration - Premium API + Agent Wallets"""
import sys
import os
import time
import json
import sqlite3
import logging

sys.path.insert(0, "/root/shared")

log = logging.getLogger("bottube.x402")

# --- Import shared x402 config (graceful fallback) ---
try:
    from x402_config import (
        X402_NETWORK, USDC_BASE, WRTC_BASE, FACILITATOR_URL,
        BOTTUBE_TREASURY, PRICE_VIDEO_STREAM_PREMIUM, PRICE_API_BULK,
        PRICE_PREMIUM_ANALYTICS, PRICE_PREMIUM_EXPORT,
        is_free, has_cdp_credentials, create_agentkit_wallet,
    )
    X402_AVAILABLE = True
except ImportError:
    X402_AVAILABLE = False
    log.warning("x402_config not found at /root/shared/x402_config.py - running without x402")

# --- Import x402 Flask middleware (optional) ---
try:
    from x402.flask.middleware import PaymentMiddleware
    X402_MIDDLEWARE = True
except ImportError:
    X402_MIDDLEWARE = False
    log.info("x402.flask not available - premium routes will be open")


# Stale facilitator hostname reported in rustchain-bounties#16871 / bottube#2210:
# x402-facilitator.cdp.coinbase.com no longer resolves (NXDOMAIN), which made
# every paid request fail with a 500 after the X-PAYMENT header was submitted.
# The current CDP facilitator lives on x402.org infrastructure; operators can
# still override via the X402_FACILITATOR_URL environment variable.
DEFAULT_FACILITATOR_URL = "https://www.x402.org/facilitator"
DEFAULT_X402_NETWORK = "base"  # eip155:8453

# bottube#2210 item 4: one exact CAIP-2 -> network-name mapping table so the id
# reported by /api/x402/info and the name the paywall compares against can never
# drift or be mis-matched by substring ("8453" would also match 84532).
CAIP2_TO_NETWORK = {
    "eip155:8453": "base",
    "base": "base",
    "eip155:84532": "base-sepolia",
    "base-sepolia": "base-sepolia",
}
# Price (USDC, decimal) each premium route must quote. The x402 middleware's Money
# path converts decimal USDC -> atomic (6 decimals), so 0.01 USDC -> 10000.
# bottube#2210 item 2: never pass an already-atomic value here (it would be
# multiplied a second time). _usdc_amount_to_atomic() is the single converter and is
# exercised directly by the 402-body test.
PREMIUM_PRICE_USDC = {
    "/api/premium/videos": 0.01,            # 10000 atomic
    "/api/premium/analytics/*": 0.005,     # 5000 atomic
    "/api/premium/trending/export": 0.01,  # 10000 atomic
}


def _network_name(network_id):
    """Return the canonical network name for a CAIP-2 id or short name."""
    return CAIP2_TO_NETWORK.get(network_id, network_id)


def _network_caip2(network_id):
    """Return the canonical CAIP-2 identifier for a network short name.

    Used by /api/x402/info to report the raw chain id while the paywall
    compares against the short name, so both ends agree on which chain.
    """
    for short, caip2 in CAIP2_TO_NETWORK.items():
        if network_id == short and caip2.startswith("eip155:"):
            return caip2
        if network_id == caip2:
            return caip2
    return network_id


def _facilitator_url():
    """Resolve the x402 facilitator URL: explicit env override always wins."""
    return os.environ.get("X402_FACILITATOR_URL") or DEFAULT_FACILITATOR_URL


def _x402_network():
    """Resolve the x402 network identifier shared by paywall and reporting paths."""
    if X402_AVAILABLE and X402_NETWORK:
        return _network_name(X402_NETWORK)
    return _network_name(os.environ.get("X402_NETWORK", DEFAULT_X402_NETWORK))


def _usdc_amount_to_atomic(amount) -> int:
    """Convert a decimal USDC amount (e.g. 0.01) to atomic units (6 decimals).

    Regression guard for bottube#2210: the paywall previously applied the 1e6
    atomic conversion to a value that was already in atomic units, quoting
    10,000 USDC for a 0.01 USDC price. Prices are always decimal USDC here;
    atomic conversion happens exactly once, at the boundary.
    """
    from decimal import Decimal, ROUND_DOWN

    value = Decimal(str(amount))
    raw = (value * (Decimal(10) ** 6)).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return int(raw)


def init_app(app, db_path):
    """Register x402 premium routes and wallet endpoints on the Flask app."""

    db_path_str = str(db_path)

    def _get_db():
        """Retrieve db. Returns a SQLite database connection.
        
        Returns:
            The result value.
        """
        conn = sqlite3.connect(db_path_str)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    # --- Ensure tables / columns exist ---
    with sqlite3.connect(db_path_str) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS x402_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payer_address TEXT NOT NULL,
            agent_id INTEGER,
            endpoint TEXT NOT NULL,
            amount_usdc TEXT NOT NULL,
            tx_hash TEXT,
            network TEXT DEFAULT 'eip155:8453',
            created_at REAL NOT NULL
        )""")
        try:
            conn.execute("ALTER TABLE agents ADD COLUMN coinbase_address TEXT DEFAULT NULL")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE agents ADD COLUMN coinbase_wallet_created INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.commit()

    # --- Determine pricing mode ---
    _all_free = True
    if X402_AVAILABLE:
        _all_free = all(
            is_free(p) for p in [
                PRICE_VIDEO_STREAM_PREMIUM, PRICE_API_BULK,
                PRICE_PREMIUM_ANALYTICS, PRICE_PREMIUM_EXPORT,
            ]
        )

    # ------------------------------------------------------------------
    # Premium Endpoints
    # ------------------------------------------------------------------
    from flask import request, jsonify as _jsonify

    @app.route("/api/premium/videos", methods=["GET"])
    def x402_premium_videos():
        """Bulk video data export with full metadata."""
        db = _get_db()
        try:
            rows = db.execute(
                "SELECT id, video_id, title, description, agent_id, views, likes, dislikes, "
                "created_at, duration_sec, thumbnail, tags, category "
                "FROM videos WHERE is_removed=0 ORDER BY created_at DESC"
            ).fetchall()
            videos = [dict(r) for r in rows]
            return _jsonify({"videos": videos, "count": len(videos), "x402": True})
        finally:
            db.close()

    @app.route("/api/premium/analytics/<agent_identifier>", methods=["GET"])
    def x402_premium_analytics(agent_identifier):
        """Deep analytics for a specific agent."""
        db = _get_db()
        try:
            agent = db.execute(
                "SELECT * FROM agents WHERE agent_name=? OR display_name=? OR id=?",
                (agent_identifier, agent_identifier, agent_identifier),
            ).fetchone()
            if not agent:
                return _jsonify({"error": "Agent not found"}), 404

            agent_id = agent["id"]
            videos = db.execute(
                "SELECT id, video_id, title, views, likes, dislikes, created_at, category "
                "FROM videos WHERE agent_id=? AND is_removed=0",
                (agent_id,),
            ).fetchall()

            total_views = sum(v["views"] or 0 for v in videos)
            total_up = sum(v["likes"] or 0 for v in videos)
            total_down = sum(v["dislikes"] or 0 for v in videos)

            return _jsonify({
                "agent": {
                    "id": agent["id"],
                    "agent_name": agent["agent_name"],
                    "display_name": agent["display_name"],
                    "bio": agent["bio"],
                    "is_human": bool(agent["is_human"]),
                },
                "videos": [dict(v) for v in videos],
                "analytics": {
                    "total_videos": len(videos),
                    "total_views": total_views,
                    "total_upvotes": total_up,
                    "total_downvotes": total_down,
                    "avg_views_per_video": round(total_views / max(len(videos), 1), 2),
                    "approval_rate": round(total_up / max(total_up + total_down, 1), 4),
                },
                "x402": True,
            })
        finally:
            db.close()

    @app.route("/api/premium/trending/export", methods=["GET"])
    def x402_premium_trending_export():
        """Full trending data with engagement scores."""
        db = _get_db()
        try:
            rows = db.execute(
                "SELECT v.id, v.video_id, v.title, v.views, v.likes, v.dislikes, "
                "v.created_at, v.category, v.tags, v.duration_sec, "
                "a.agent_name, a.display_name "
                "FROM videos v LEFT JOIN agents a ON v.agent_id = a.id "
                "WHERE v.is_removed=0 ORDER BY v.views DESC LIMIT 100"
            ).fetchall()
            return _jsonify({"trending": [dict(r) for r in rows], "count": len(rows), "x402": True})
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Wallet Endpoints
    # ------------------------------------------------------------------

    def _resolve_api_key():
        """Resolve the caller's API key.

        The rest of the BoTTube API authenticates with the X-API-Key header,
        but these wallet/payment endpoints only read `Authorization: Bearer`,
        so agents sending X-API-Key got a 401 (bottube#2210, item 3).
        Accept either: X-API-Key first (platform convention), then
        Authorization: Bearer for callers that already use it.
        """
        api_key = request.headers.get("X-API-Key", "").strip()
        if not api_key:
            api_key = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        return api_key or None

    @app.route("/api/agents/me/coinbase-wallet", methods=["GET"])
    def x402_get_agent_wallet():
        """Get agent's Coinbase wallet info."""
        api_key = _resolve_api_key()
        if not api_key:
            return _jsonify({"error": "API key required"}), 401
        db = _get_db()
        try:
            agent = db.execute(
                "SELECT id, agent_name, display_name, coinbase_address, coinbase_wallet_created "
                "FROM agents WHERE api_key=?",
                (api_key,),
            ).fetchone()
            if not agent:
                return _jsonify({"error": "Invalid API key"}), 401
            return _jsonify({
                "agent": agent["agent_name"],
                "display_name": agent["display_name"],
                "coinbase_address": agent["coinbase_address"],
                "wallet_created_via_agentkit": bool(agent["coinbase_wallet_created"]),
                "network": "Base (eip155:8453)",
                "wrtc_contract": WRTC_BASE if X402_AVAILABLE else None,
            })
        finally:
            db.close()

    @app.route("/api/agents/me/coinbase-wallet", methods=["POST"])
    def x402_create_agent_wallet():
        """Create or link Coinbase wallet for agent."""
        api_key = _resolve_api_key()
        if not api_key:
            return _jsonify({"error": "API key required"}), 401

        data = request.get_json(silent=True) or {}
        manual_address = data.get("coinbase_address")

        db = _get_db()
        try:
            agent = db.execute(
                "SELECT id, agent_name, coinbase_address FROM agents WHERE api_key=?",
                (api_key,),
            ).fetchone()
            if not agent:
                return _jsonify({"error": "Invalid API key"}), 401

            if manual_address:
                # Basic validation: 0x + 40 hex chars
                if not (manual_address.startswith("0x") and len(manual_address) == 42):
                    return _jsonify({"error": "Invalid Ethereum address format"}), 400
                db.execute(
                    "UPDATE agents SET coinbase_address=?, coinbase_wallet_created=0 WHERE id=?",
                    (manual_address, agent["id"]),
                )
                db.commit()
                return _jsonify({
                    "ok": True,
                    "agent": agent["agent_name"],
                    "coinbase_address": manual_address,
                    "method": "manual_link",
                })

            # Try AgentKit auto-creation
            if not X402_AVAILABLE:
                return _jsonify({
                    "error": "x402 module not available",
                    "hint": "Use manual linking: POST with {\"coinbase_address\": \"0x...\"}",
                }), 503
            try:
                if not has_cdp_credentials():
                    return _jsonify({
                        "error": "CDP credentials not configured on server",
                        "hint": "Use manual linking: POST with {\"coinbase_address\": \"0x...\"}",
                    }), 503
                address, _wallet_data = create_agentkit_wallet()
                db.execute(
                    "UPDATE agents SET coinbase_address=?, coinbase_wallet_created=1 WHERE id=?",
                    (address, agent["id"]),
                )
                db.commit()
                return _jsonify({
                    "ok": True,
                    "agent": agent["agent_name"],
                    "coinbase_address": address,
                    "method": "agentkit",
                })
            except Exception as e:
                return _jsonify({
                    "error": "AgentKit wallet creation failed: " + str(e),
                    "hint": "Use manual linking: POST with {\"coinbase_address\": \"0x...\"}",
                }), 503
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Payment History + Info
    # ------------------------------------------------------------------

    @app.route("/api/x402/payments", methods=["GET"])
    def x402_payment_history():
        """View x402 payment history."""
        api_key = _resolve_api_key()
        db = _get_db()
        try:
            if api_key:
                agent = db.execute("SELECT id FROM agents WHERE api_key=?", (api_key,)).fetchone()
                if agent:
                    payments = db.execute(
                        "SELECT * FROM x402_payments WHERE agent_id=? ORDER BY created_at DESC LIMIT 50",
                        (agent["id"],),
                    ).fetchall()
                    return _jsonify({"payments": [dict(p) for p in payments]})

            # Public summary (no key or invalid key)
            row = db.execute("SELECT COUNT(*) as cnt FROM x402_payments").fetchone()
            return _jsonify({
                "total_payments": row["cnt"],
                "hint": "Provide Bearer API key for detailed history",
            })
        finally:
            db.close()

    @app.route("/api/x402/info", methods=["GET"])
    def x402_info():
        """Public x402 integration info."""
        return _jsonify({
            "x402_enabled": X402_AVAILABLE,
            "network": _network_caip2(_x402_network()),
            "facilitator": _facilitator_url(),
            "payment_token": USDC_BASE if X402_AVAILABLE else None,
            "wrtc_token": WRTC_BASE if X402_AVAILABLE else None,
            "treasury": BOTTUBE_TREASURY if X402_AVAILABLE else None,
            "premium_endpoints": [
                {"path": "/api/premium/videos", "price_usdc": PRICE_VIDEO_STREAM_PREMIUM if X402_AVAILABLE else "0"},
                {"path": "/api/premium/analytics/<agent>", "price_usdc": PRICE_PREMIUM_ANALYTICS if X402_AVAILABLE else "0"},
                {"path": "/api/premium/trending/export", "price_usdc": PRICE_PREMIUM_EXPORT if X402_AVAILABLE else "0"},
            ],
            "pricing_mode": "free" if (not X402_AVAILABLE or _all_free) else "paid",
            "wallet_endpoints": [
                {"path": "/api/agents/me/coinbase-wallet", "methods": ["GET", "POST"]},
            ],
        })

    # ------------------------------------------------------------------
    # x402 WSGI Payment Middleware (path-based paywall)
    # ------------------------------------------------------------------
    if X402_MIDDLEWARE and X402_AVAILABLE and not _all_free:
        _addr = BOTTUBE_TREASURY or "0x0000000000000000000000000000000000000000"
        # bottube#2210 items 1 + 2 + 4: resolve network and price from the
        # single-source-of-truth mapping table and atomic-price dict so the
        # /info endpoint and the middleware 402 body can never disagree, and
        # wire _usdc_amount_to_atomic() so the decimal USDC prices in
        # PREMIUM_PRICE_USDC are never passed raw to the middleware.
        _net = _x402_network()
        mw = PaymentMiddleware(app)
        if not is_free(PRICE_VIDEO_STREAM_PREMIUM):
            _price = _usdc_amount_to_atomic(PREMIUM_PRICE_USDC.get("/api/premium/videos", 0.01))
            mw.add(price=_price, pay_to_address=_addr,
                   path="/api/premium/videos", network=_net,
                   description="Bulk video data export")
        if not is_free(PRICE_PREMIUM_ANALYTICS):
            _price = _usdc_amount_to_atomic(PREMIUM_PRICE_USDC.get("/api/premium/analytics/*", 0.005))
            mw.add(price=_price, pay_to_address=_addr,
                   path="/api/premium/analytics/*", network=_net,
                   description="Deep agent analytics")
        if not is_free(PRICE_PREMIUM_EXPORT):
            _price = _usdc_amount_to_atomic(PREMIUM_PRICE_USDC.get("/api/premium/trending/export", 0.01))
            mw.add(price=_price, pay_to_address=_addr,
                   path="/api/premium/trending/export", network=_net,
                   description="Trending data export")
        print("[x402] Payment middleware active on /api/premium/* routes")

    _route_count = 7  # premium(3) + wallet(2) + payments(1) + info(1)
    mode = "free" if _all_free else "paid"
    print("[x402] BoTTube x402 module loaded: {} routes, mode={}, middleware={}".format(
        _route_count, mode, "yes" if X402_MIDDLEWARE else "no"))
