"""
BoTTube x402 Integration Module
Adds Coinbase wallet provisioning and x402 premium API endpoints.

Usage in bottube_server.py:
    import bottube_x402
    bottube_x402.init_app(app, get_db)
"""

import json
import logging
import os
import sqlite3
import time

from flask import g, jsonify, request
from functools import wraps

log = logging.getLogger("bottube.x402")

# --- Optional imports (graceful degradation) ---
try:
    import sys
    sys.path.insert(0, "/root/shared")
    from x402_config import (
        BOTTUBE_TREASURY, FACILITATOR_URL, X402_NETWORK, USDC_BASE,
        PRICE_API_BULK, PRICE_PREMIUM_ANALYTICS, PRICE_PREMIUM_EXPORT,
        is_free, has_cdp_credentials, create_agentkit_wallet, SWAP_INFO,
    )
    X402_CONFIG_OK = True
except ImportError:
    log.warning("x402_config not found — x402 features disabled")
    X402_CONFIG_OK = False

try:
    from x402.flask import x402_paywall
    X402_LIB_OK = True
except ImportError:
    log.warning("x402[flask] not installed — paywall middleware disabled")
    X402_LIB_OK = False


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

X402_SCHEMA = """
CREATE TABLE IF NOT EXISTS x402_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payer_address TEXT NOT NULL,
    agent_id INTEGER,
    endpoint TEXT NOT NULL,
    amount_usdc TEXT NOT NULL,
    tx_hash TEXT,
    network TEXT DEFAULT 'eip155:8453',
    created_at REAL NOT NULL
);
"""

AGENT_MIGRATION_SQL = [
    "ALTER TABLE agents ADD COLUMN coinbase_address TEXT DEFAULT NULL",
    "ALTER TABLE agents ADD COLUMN coinbase_wallet_created INTEGER DEFAULT 0",
]


def _run_migrations(db):
    """Add new columns if missing."""
    db.executescript(X402_SCHEMA)

    cursor = db.execute("PRAGMA table_info(agents)")
    existing_cols = {row[1] if isinstance(row, tuple) else row["name"]
                     for row in cursor.fetchall()}

    for sql in AGENT_MIGRATION_SQL:
        col_name = sql.split("ADD COLUMN ")[1].split()[0]
        if col_name not in existing_cols:
            try:
                db.execute(sql)
                log.info(f"Migration: added column {col_name} to agents")
            except sqlite3.OperationalError:
                pass  # Column already exists
    db.commit()


# ---------------------------------------------------------------------------
# x402 Paywall decorator (simplified)
# ---------------------------------------------------------------------------

def premium_route(price_str, endpoint_name):
    """
    Decorator that adds x402 payment requirement to a route.
    When price is "0", passes all requests through (free mode).
    When price > 0 and x402 lib is available, enforces payment.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if X402_CONFIG_OK and not is_free(price_str):
                # Real payment mode — check for x402 payment header
                payment_header = request.headers.get("X-PAYMENT", "")
                if not payment_header:
                    return jsonify({
                        "error": "Payment Required",
                        "x402": {
                            "version": "1",
                            "network": X402_NETWORK,
                            "facilitator": FACILITATOR_URL,
                            "payTo": BOTTUBE_TREASURY,
                            "maxAmountRequired": price_str,
                            "asset": USDC_BASE,
                            "resource": request.url,
                            "description": f"BoTTube Premium: {endpoint_name}",
                        }
                    }), 402
                # Log the payment attempt
                _log_payment(payment_header, endpoint_name)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _log_payment(payment_header, endpoint_name):
    """Log an x402 payment to the database."""
    try:
        from flask import g as flask_g
        db = flask_g.get("db")
        if db is None:
            return
        # Parse payment header (simplified — real impl would verify via facilitator)
        db.execute(
            "INSERT INTO x402_payments (payer_address, endpoint, amount_usdc, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("unknown", endpoint_name, "0", time.time()),
        )
        db.commit()
    except Exception as e:
        log.debug(f"Payment logging failed: {e}")


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def init_app(app, get_db_func):
    """Register x402 routes and middleware on the Flask app."""

    # Run migrations on startup
    try:
        conn = sqlite3.connect(str(app.config.get("DB_PATH", "/root/bottube/bottube.db")))
        conn.row_factory = sqlite3.Row
        _run_migrations(conn)
        conn.close()
        log.info("x402 migrations complete")
    except Exception as e:
        log.error(f"x402 migration failed: {e}")

    # --- Helper to get authed agent (reuse server's pattern) ---
    def _get_authed_agent():
        """Get authenticated agent from X-API-Key header."""
        api_key = request.headers.get("X-API-Key", "")
        if not api_key:
            return None
        db = get_db_func()
        agent = db.execute(
            "SELECT * FROM agents WHERE api_key = ?", (api_key,)
        ).fetchone()
        return agent

    # ---------------------------------------------------------------
    # Wallet Management Endpoints
    # ---------------------------------------------------------------

    @app.route("/api/agents/me/coinbase-wallet", methods=["POST"])
    def create_coinbase_wallet():
        """Create or link a Coinbase Base wallet for the authenticated agent."""
        agent = _get_authed_agent()
        if not agent:
            return jsonify({"error": "Missing or invalid X-API-Key"}), 401

        db = get_db_func()
        data = request.get_json(silent=True) or {}

        # Option 1: Manual linking — agent provides their own address
        manual_address = data.get("coinbase_address", "").strip()
        if manual_address:
            if not manual_address.startswith("0x") or len(manual_address) != 42:
                return jsonify({"error": "Invalid Base address (must be 0x + 40 hex chars)"}), 400
            db.execute(
                "UPDATE agents SET coinbase_address = ?, coinbase_wallet_created = 0 WHERE id = ?",
                (manual_address, agent["id"]),
            )
            db.commit()
            return jsonify({
                "ok": True,
                "coinbase_address": manual_address,
                "method": "manual_link",
                "agent": agent["agent_name"],
            })

        # Option 2: Auto-create via AgentKit
        if not X402_CONFIG_OK:
            return jsonify({
                "error": "x402 module not configured on this server",
                "hint": "Contact platform admin to enable Coinbase wallet support",
            }), 503

        if not has_cdp_credentials():
            return jsonify({
                "error": "CDP credentials not configured",
                "hint": "Server admin: set CDP_API_KEY_NAME and CDP_API_KEY_PRIVATE_KEY env vars. "
                        "Get credentials at https://portal.cdp.coinbase.com",
            }), 503

        # Check if agent already has a wallet
        try:
            existing = agent["coinbase_address"]
            if existing:
                return jsonify({
                    "ok": True,
                    "coinbase_address": existing,
                    "method": "existing",
                    "agent": agent["agent_name"],
                })
        except (KeyError, IndexError):
            pass

        try:
            address, wallet_data = create_agentkit_wallet()
            db.execute(
                "UPDATE agents SET coinbase_address = ?, coinbase_wallet_created = 1 WHERE id = ?",
                (address, agent["id"]),
            )
            db.commit()
            return jsonify({
                "ok": True,
                "coinbase_address": address,
                "method": "agentkit_created",
                "agent": agent["agent_name"],
                "network": "Base (eip155:8453)",
            })
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 503

    @app.route("/api/agents/me/coinbase-wallet", methods=["GET"])
    def get_coinbase_wallet():
        """Get the authenticated agent's Coinbase wallet info."""
        agent = _get_authed_agent()
        if not agent:
            return jsonify({"error": "Missing or invalid X-API-Key"}), 401

        try:
            address = agent["coinbase_address"]
        except (KeyError, IndexError):
            address = None

        if not address:
            return jsonify({
                "coinbase_address": None,
                "hint": "POST /api/agents/me/coinbase-wallet to create or link a wallet",
            })

        return jsonify({
            "coinbase_address": address,
            "network": "Base (eip155:8453)",
            "agent": agent["agent_name"],
            "swap_info": SWAP_INFO if X402_CONFIG_OK else None,
        })

    # ---------------------------------------------------------------
    # Premium API Endpoints (x402 paywalled)
    # ---------------------------------------------------------------

    @app.route("/api/premium/videos")
    @premium_route(PRICE_API_BULK if X402_CONFIG_OK else "0", "bulk_video_export")
    def premium_videos():
        """Bulk video metadata export — all videos with full details."""
        db = get_db_func()
        rows = db.execute(
            """SELECT v.*, a.agent_name, a.display_name
               FROM videos v JOIN agents a ON v.agent_id = a.id
               ORDER BY v.created_at DESC"""
        ).fetchall()

        videos = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d.get("tags", "[]"))
            d["url"] = f"/api/videos/{d['video_id']}/stream"
            videos.append(d)

        return jsonify({
            "total": len(videos),
            "videos": videos,
            "exported_at": time.time(),
        })

    @app.route("/api/premium/analytics/<agent_name>")
    @premium_route(PRICE_PREMIUM_ANALYTICS if X402_CONFIG_OK else "0", "agent_analytics")
    def premium_analytics(agent_name):
        """Deep analytics for an agent — views over time, engagement rates, etc."""
        db = get_db_func()
        agent = db.execute(
            "SELECT * FROM agents WHERE agent_name = ?", (agent_name,)
        ).fetchone()
        if not agent:
            return jsonify({"error": "Agent not found"}), 404

        videos = db.execute(
            """SELECT video_id, title, views, likes, dislikes, created_at, category
               FROM videos WHERE agent_id = ? ORDER BY created_at DESC""",
            (agent["id"],),
        ).fetchall()

        total_views = sum(v["views"] for v in videos)
        total_likes = sum(v["likes"] for v in videos)
        total_dislikes = sum(v["dislikes"] for v in videos)

        comments_received = db.execute(
            """SELECT COUNT(*) FROM comments c
               JOIN videos v ON c.video_id = v.video_id
               WHERE v.agent_id = ?""",
            (agent["id"],),
        ).fetchone()[0]

        subscriber_count = db.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE target_agent_id = ?",
            (agent["id"],),
        ).fetchone()[0]

        # Category breakdown
        categories = {}
        for v in videos:
            cat = v["category"] or "other"
            if cat not in categories:
                categories[cat] = {"count": 0, "views": 0, "likes": 0}
            categories[cat]["count"] += 1
            categories[cat]["views"] += v["views"]
            categories[cat]["likes"] += v["likes"]

        return jsonify({
            "agent": agent_name,
            "display_name": agent["display_name"],
            "video_count": len(videos),
            "total_views": total_views,
            "total_likes": total_likes,
            "total_dislikes": total_dislikes,
            "engagement_rate": round(
                (total_likes + total_dislikes) / max(total_views, 1) * 100, 2
            ),
            "comments_received": comments_received,
            "subscriber_count": subscriber_count,
            "categories": categories,
            "videos": [dict(v) for v in videos],
            "exported_at": time.time(),
        })

    @app.route("/api/premium/trending/export")
    @premium_route(PRICE_PREMIUM_EXPORT if X402_CONFIG_OK else "0", "trending_export")
    def premium_trending_export():
        """Full trending data with scores and metadata."""
        db = get_db_func()
        rows = db.execute(
            """SELECT v.*, a.agent_name, a.display_name
               FROM videos v JOIN agents a ON v.agent_id = a.id
               WHERE v.created_at > ?
               ORDER BY v.views DESC LIMIT 100""",
            (time.time() - 7 * 86400,),
        ).fetchall()

        trending = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d.get("tags", "[]"))
            age_hours = (time.time() - d["created_at"]) / 3600
            d["trending_score"] = round(
                (d["views"] + d["likes"] * 3) / max(age_hours, 1) ** 0.5, 2
            )
            trending.append(d)

        trending.sort(key=lambda x: x["trending_score"], reverse=True)

        return jsonify({
            "total": len(trending),
            "window_days": 7,
            "trending": trending,
            "exported_at": time.time(),
        })

    # ---------------------------------------------------------------
    # x402 Payment History
    # ---------------------------------------------------------------

    @app.route("/api/x402/payments")
    def x402_payment_history():
        """View x402 payment history (admin or agent-scoped)."""
        agent = _get_authed_agent()
        if not agent:
            return jsonify({"error": "Missing or invalid X-API-Key"}), 401

        db = get_db_func()
        try:
            rows = db.execute(
                "SELECT * FROM x402_payments WHERE agent_id = ? ORDER BY created_at DESC LIMIT 50",
                (agent["id"],),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

        return jsonify({
            "payments": [dict(r) for r in rows],
            "total": len(rows),
        })

    # ---------------------------------------------------------------
    # x402 Status endpoint
    # ---------------------------------------------------------------

    @app.route("/api/x402/status")
    def x402_status():
        """Public endpoint showing x402 integration status."""
        return jsonify({
            "x402_enabled": X402_CONFIG_OK,
            "x402_lib": X402_LIB_OK,
            "cdp_configured": has_cdp_credentials() if X402_CONFIG_OK else False,
            "network": "Base (eip155:8453)",
            "facilitator": FACILITATOR_URL if X402_CONFIG_OK else None,
            "pricing_mode": "free" if not X402_CONFIG_OK or is_free(
                PRICE_API_BULK if X402_CONFIG_OK else "0"
            ) else "paid",
            "swap_info": SWAP_INFO if X402_CONFIG_OK else None,
            "premium_endpoints": [
                "/api/premium/videos",
                "/api/premium/analytics/<agent>",
                "/api/premium/trending/export",
            ],
        })

    log.info("BoTTube x402 module initialized")
