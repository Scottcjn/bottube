# SPDX-License-Identifier: MIT
"""BoTTube x402 Integration - Premium API + Agent Wallets"""
import fnmatch
import inspect
import sys
import os
import re
import sqlite3
import logging
from decimal import Decimal
from urllib.parse import urlparse

sys.path.insert(0, "/root/shared")

log = logging.getLogger("bottube.x402")

# --- Import shared x402 config (graceful fallback) ---
try:
    from x402_config import (
        X402_NETWORK, USDC_BASE, FACILITATOR_URL,
        BOTTUBE_TREASURY, PRICE_VIDEO_STREAM_PREMIUM,
        PRICE_PREMIUM_ANALYTICS, PRICE_PREMIUM_EXPORT,
        is_free, has_cdp_credentials, create_agentkit_wallet,
    )
    X402_AVAILABLE = True
except ImportError:
    X402_AVAILABLE = False
    log.warning("x402_config not found at /root/shared/x402_config.py - running without x402")

# Optional hook: a callable returning facilitator auth headers, in the shape
# the x402 SDK's FacilitatorConfig["create_headers"] expects. Hosted mainnet
# facilitators (for example Coinbase CDP) require authenticated requests.
# The SDK awaits this hook, so it may be an async callable; a plain sync
# callable is wrapped in an async shim by _async_headers_hook().
try:
    from x402_config import facilitator_create_headers as _FACILITATOR_CREATE_HEADERS
except ImportError:
    _FACILITATOR_CREATE_HEADERS = None

# --- Import x402 Flask middleware (optional) ---
try:
    from x402.flask.middleware import PaymentMiddleware
    X402_MIDDLEWARE = True
except ImportError:
    X402_MIDDLEWARE = False
    log.info("x402.flask not available - paid premium routes will return 503")


USDC_DECIMALS = 6
_ATOMIC_PRICE_RE = re.compile(r"^[0-9]+$")

# x402_config uses CAIP-2 ids. The legacy x402 SDK (x402.flask.middleware)
# only accepts its own short names, so map explicitly and never guess.
_CAIP2_TO_SDK_NETWORK = {
    "eip155:8453": "base",
    "eip155:84532": "base-sepolia",
}
_MAINNET_SDK_NETWORKS = {"base"}

# The public x402.org facilitator only settles testnet payments. It must
# never be used (or defaulted to) for a mainnet paywall.
_TESTNET_ONLY_FACILITATOR_HOSTS = {"x402.org", "www.x402.org"}


def _sdk_network(caip2):
    """Map a CAIP-2 network id to the legacy SDK network name, or None."""
    return _CAIP2_TO_SDK_NETWORK.get(str(caip2 or "").strip().lower())


def _atomic_to_usdc(price):
    """Convert a USDC atomic-unit price string ("10000") to a decimal string ("0.01").

    x402_config documents every PRICE_* value as USDC atomic units (6 decimals).
    Anything that is not a plain non-negative integer string is rejected rather
    than reinterpreted, because guessing units is how a 0.01 USDC price turned
    into 10,000 USDC.
    """
    text = str(price).strip()
    if not _ATOMIC_PRICE_RE.match(text):
        raise ValueError("price must be USDC atomic units (digits only), got %r" % (price,))
    usdc = Decimal(text) / (Decimal(10) ** USDC_DECIMALS)
    return format(usdc.normalize(), "f")


def _atomic_to_sdk_money(price):
    """Return the legacy SDK Money string for an atomic-unit price.

    x402.common.process_price_to_atomic_amount treats a str/int price as USD
    and multiplies by 10**6 itself, so it must receive "$0.01", not "10000".
    """
    return "$" + _atomic_to_usdc(price)


def _async_headers_hook(hook):
    """Return an awaitable-returning version of a facilitator headers hook.

    x402 0.3.0 FacilitatorClient.verify/settle run
    ``await self.config["create_headers"]()``. Passing a plain sync function
    makes every paid request fail with a TypeError, so wrap it.
    """
    if inspect.iscoroutinefunction(hook):
        return hook

    async def _create_headers():
        result = hook()
        if inspect.isawaitable(result):
            result = await result
        return result

    return _create_headers


def _facilitator_config(sdk_network):
    """Build the SDK FacilitatorConfig for the paywall.

    Returns (config, reason). config is None when no usable facilitator is
    configured, in which case the paid routes fail closed.
    """
    url = (os.environ.get("X402_FACILITATOR_URL") or FACILITATOR_URL or "").strip().rstrip("/")
    if not url:
        return None, "no_facilitator_configured"
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None, "facilitator_url_must_be_https"
    if sdk_network in _MAINNET_SDK_NETWORKS and parsed.hostname.lower() in _TESTNET_ONLY_FACILITATOR_HOSTS:
        return None, "testnet_only_facilitator_on_mainnet"
    config = {"url": url}
    if _FACILITATOR_CREATE_HEADERS is not None:
        config["create_headers"] = _async_headers_hook(_FACILITATOR_CREATE_HEADERS)
    return config, None


def _extract_api_key(req):
    """Read the agent API key from X-API-Key, falling back to Authorization: Bearer."""
    key = (req.headers.get("X-API-Key") or "").strip()
    if key:
        return key
    auth = (req.headers.get("Authorization") or "").strip()
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return ""


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

    # --- Determine pricing mode and paywall plan ---
    # (route pattern, public path, config price, description)
    _premium_routes = []
    if X402_AVAILABLE:
        _premium_routes = [
            ("/api/premium/videos", "/api/premium/videos",
             PRICE_VIDEO_STREAM_PREMIUM, "Bulk video data export"),
            ("/api/premium/analytics/*", "/api/premium/analytics/<agent>",
             PRICE_PREMIUM_ANALYTICS, "Deep agent analytics"),
            ("/api/premium/trending/export", "/api/premium/trending/export",
             PRICE_PREMIUM_EXPORT, "Trending data export"),
        ]
    _paid_routes = [r for r in _premium_routes if not is_free(r[2])]
    _all_free = not _paid_routes

    _sdk_net = _sdk_network(X402_NETWORK) if X402_AVAILABLE else None
    _facilitator = None
    _paywall_problem = None
    if _paid_routes:
        if not X402_MIDDLEWARE:
            _paywall_problem = "x402_sdk_not_installed"
        elif not _sdk_net:
            _paywall_problem = "unsupported_network"
        elif not BOTTUBE_TREASURY:
            _paywall_problem = "treasury_not_configured"
        else:
            _facilitator, _paywall_problem = _facilitator_config(_sdk_net)
        if _paywall_problem is None:
            try:
                for _pattern, _public, _price, _desc in _paid_routes:
                    _atomic_to_sdk_money(_price)
            except ValueError as exc:
                log.error("x402 price config invalid: %s", exc)
                _paywall_problem = "invalid_price_config"

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
        api_key = _extract_api_key(request)
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
            })
        finally:
            db.close()

    @app.route("/api/agents/me/coinbase-wallet", methods=["POST"])
    def x402_create_agent_wallet():
        """Create or link Coinbase wallet for agent."""
        api_key = _extract_api_key(request)
        if not api_key:
            return _jsonify({"error": "API key required"}), 401

        data = request.get_json(silent=True)
        if data is None:
            data = {}
        elif not isinstance(data, dict):
            return _jsonify({"error": "JSON body must be an object"}), 400
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
        api_key = _extract_api_key(request)
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
                "hint": "Provide X-API-Key (or Authorization: Bearer) for detailed history",
            })
        finally:
            db.close()

    def _endpoint_price(price):
        """Describe a config price for /api/x402/info in USDC and atomic units."""
        if not X402_AVAILABLE or is_free(price):
            return {"price_usdc": "0", "price_atomic": "0"}
        try:
            return {"price_usdc": _atomic_to_usdc(price), "price_atomic": str(price).strip()}
        except ValueError:
            return {"price_usdc": None, "price_atomic": None}

    @app.route("/api/x402/info", methods=["GET"])
    def x402_info():
        """Public x402 integration info."""
        if _all_free:
            pricing_mode = "free"
        elif _paywall_problem:
            pricing_mode = "unavailable"
        else:
            pricing_mode = "paid"
        body = {
            "x402_enabled": X402_AVAILABLE,
            "network": X402_NETWORK if X402_AVAILABLE else None,
            "network_name": _sdk_net,
            "facilitator": _facilitator["url"] if _facilitator and not _paywall_problem else None,
            "payment_token": USDC_BASE if X402_AVAILABLE else None,
            "treasury": BOTTUBE_TREASURY if X402_AVAILABLE else None,
            "premium_endpoints": [
                dict({"path": public}, **_endpoint_price(price))
                for _pattern, public, price, _desc in _premium_routes
            ] or [
                {"path": "/api/premium/videos", "price_usdc": "0", "price_atomic": "0"},
                {"path": "/api/premium/analytics/<agent>", "price_usdc": "0", "price_atomic": "0"},
                {"path": "/api/premium/trending/export", "price_usdc": "0", "price_atomic": "0"},
            ],
            "pricing_mode": pricing_mode,
            "wallet_endpoints": [
                {"path": "/api/agents/me/coinbase-wallet", "methods": ["GET", "POST"]},
            ],
        }
        if pricing_mode == "unavailable":
            body["unavailable_reason"] = _paywall_problem
        return _jsonify(body)

    # ------------------------------------------------------------------
    # x402 WSGI Payment Middleware (path-based paywall)
    # ------------------------------------------------------------------
    if _paid_routes and not _paywall_problem:
        mw = PaymentMiddleware(app)
        for pattern, _public, price, desc in _paid_routes:
            mw.add(
                price=_atomic_to_sdk_money(price),
                pay_to_address=BOTTUBE_TREASURY,
                path=pattern,
                network=_sdk_net,
                description=desc,
                facilitator_config=_facilitator,
            )
        print("[x402] Payment middleware active on /api/premium/* routes "
              "(network={}, facilitator={})".format(_sdk_net, _facilitator["url"]))
    elif _paid_routes:
        # A price is configured but the paywall cannot collect it. Fail closed:
        # never serve paid data for free, and never quote a price that no
        # facilitator can settle.
        _blocked = [pattern for pattern, _public, _price, _desc in _paid_routes]

        @app.before_request
        def _x402_paywall_unavailable():
            # Same matching rules as the SDK middleware (glob or exact).
            path = request.path
            if not any(
                fnmatch.fnmatch(path, pattern) if "*" in pattern else path == pattern
                for pattern in _blocked
            ):
                return None
            return _jsonify({
                "error": "payment_unavailable",
                "reason": _paywall_problem,
                "protocol": "x402",
            }), 503

        log.error("x402 paywall disabled (%s); paid premium routes return 503", _paywall_problem)
        print("[x402] Paywall unavailable ({}); paid premium routes return 503".format(_paywall_problem))

    _route_count = 7  # premium(3) + wallet(2) + payments(1) + info(1)
    mode = "free" if _all_free else ("unavailable" if _paywall_problem else "paid")
    print("[x402] BoTTube x402 module loaded: {} routes, mode={}, middleware={}".format(
        _route_count, mode, "yes" if X402_MIDDLEWARE else "no"))
