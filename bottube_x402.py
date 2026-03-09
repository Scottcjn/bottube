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


def init_app(app, db_path):
    """Register x402 premium routes and wallet endpoints on the Flask app."""

    db_path_str = str(db_path)

    def _get_db():
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

    @app.route("/api/agents/me/coinbase-wallet", methods=["GET"])
    def x402_get_agent_wallet():
        """Get agent's Coinbase wallet info."""
        api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
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
        api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
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
        api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
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
            "network": X402_NETWORK if X402_AVAILABLE else None,
            "facilitator": FACILITATOR_URL if X402_AVAILABLE else None,
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
        _net = "base" if "8453" in X402_NETWORK else "base-sepolia"
        mw = PaymentMiddleware(app)
        if not is_free(PRICE_VIDEO_STREAM_PREMIUM):
            mw.add(price=PRICE_VIDEO_STREAM_PREMIUM, pay_to_address=_addr,
                   path="/api/premium/videos", network=_net,
                   description="Bulk video data export")
        if not is_free(PRICE_PREMIUM_ANALYTICS):
            mw.add(price=PRICE_PREMIUM_ANALYTICS, pay_to_address=_addr,
                   path="/api/premium/analytics/*", network=_net,
                   description="Deep agent analytics")
        if not is_free(PRICE_PREMIUM_EXPORT):
            mw.add(price=PRICE_PREMIUM_EXPORT, pay_to_address=_addr,
                   path="/api/premium/trending/export", network=_net,
                   description="Trending data export")
        print("[x402] Payment middleware active on /api/premium/* routes")

    _route_count = 7  # premium(3) + wallet(2) + payments(1) + info(1)
    mode = "free" if _all_free else "paid"
    print("[x402] BoTTube x402 module loaded: {} routes, mode={}, middleware={}".format(
        _route_count, mode, "yes" if X402_MIDDLEWARE else "no"))
