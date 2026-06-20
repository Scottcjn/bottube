"""
RTC Service Gateway — Pay RTC for Real Services
=================================================
Turns RTC from a mined token into a prepaid service credit.
Users buy RTC from miners (OTC), then spend it on BoTTube services.

Services:
  - Pro API Day Pass (10 RTC) — premium endpoints for 24 hours
  - Render Credits (15 RTC) — generate AI video via LTX pipeline
  - POWER8 Inference (3 RTC) — chat with GPT-OSS 120B

Flow:
  1. User has rtc_balance (earned mining or bought OTC)
  2. POST /api/rtc/pay → debit balance, return service_token
  3. Use service_token to access gated endpoints
  4. Token expires after TTL

Author: Scott Boudreaux, Elyan Labs
"""

import hashlib
import json
import logging
import secrets
import sqlite3
import time

from flask import Blueprint, g, jsonify, request

log = logging.getLogger("bottube.rtc_services")

rtc_services_bp = Blueprint("rtc_services", __name__)

# ---------------------------------------------------------------------------
# Service Catalog
# ---------------------------------------------------------------------------

SERVICE_CATALOG = {
    "pro_api_day": {
        "name": "Pro API Day Pass",
        "description": "24-hour access to premium analytics, trending export, and reputation endpoints",
        "price_rtc": 10.0,
        "token_ttl_sec": 86400,  # 24 hours
        "uses_total": 1000,      # 1000 API calls
        "scope": {"tier": "pro", "endpoints": [
            "/api/premium/analytics",
            "/api/premium/trending/export",
            "/api/premium/reputation",
        ]},
    },
    "pro_api_month": {
        "name": "Pro API Monthly Pass",
        "description": "30-day access to all premium endpoints",
        "price_rtc": 60.0,
        "token_ttl_sec": 2592000,  # 30 days
        "uses_total": 30000,
        "scope": {"tier": "pro", "endpoints": "all_premium"},
    },
    "render_standard": {
        "name": "AI Video Render",
        "description": "Generate one AI video via LTX-2.3 pipeline on local GPU",
        "price_rtc": 15.0,
        "token_ttl_sec": 3600,   # 1 hour to use
        "uses_total": 1,
        "scope": {"tier": "render", "job_type": "video_render"},
    },
    "render_variant": {
        "name": "AI Video Variant / Retry",
        "description": "Re-render or variant of an existing video",
        "price_rtc": 5.0,
        "token_ttl_sec": 3600,
        "uses_total": 1,
        "scope": {"tier": "render", "job_type": "video_variant"},
    },
    "inference_single": {
        "name": "POWER8 Deep Chat",
        "description": "One chat request to GPT-OSS 120B on IBM POWER8 S824 (512GB RAM)",
        "price_rtc": 3.0,
        "token_ttl_sec": 300,    # 5 minutes to use
        "uses_total": 1,
        "scope": {"tier": "inference", "model": "gpt-oss-120b"},
    },
    "inference_pack": {
        "name": "POWER8 Chat Pack (20 requests)",
        "description": "20 chat requests to GPT-OSS 120B",
        "price_rtc": 25.0,
        "token_ttl_sec": 604800,  # 7 days
        "uses_total": 20,
        "scope": {"tier": "inference", "model": "gpt-oss-120b"},
    },
    "attestation_cert": {
        "name": "Hardware Attestation Certificate",
        "description": "Verified hardware fingerprint report for DePIN compliance",
        "price_rtc": 20.0,
        "token_ttl_sec": 86400,
        "uses_total": 1,
        "scope": {"tier": "attestation", "type": "full_report"},
    },
}


# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------

def init_service_tables(db_path):
    """Create service tables if they don't exist."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS service_catalog (
            service_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price_rtc REAL NOT NULL,
            token_ttl_sec INTEGER NOT NULL,
            uses_total INTEGER DEFAULT 1,
            scope_json TEXT DEFAULT '{}',
            active INTEGER DEFAULT 1,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )""")

        conn.execute("""CREATE TABLE IF NOT EXISTS service_purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            service_key TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            amount_rtc REAL NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'active',
            scope_json TEXT DEFAULT '{}',
            uses_total INTEGER DEFAULT 1,
            uses_remaining INTEGER DEFAULT 1,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            redeemed_at REAL DEFAULT 0,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )""")

        conn.execute("""CREATE INDEX IF NOT EXISTS idx_sp_agent
            ON service_purchases(agent_id, created_at DESC)""")
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_sp_token
            ON service_purchases(token_hash, status, expires_at)""")

        # Seed catalog from Python dict
        now = time.time()
        for key, svc in SERVICE_CATALOG.items():
            conn.execute("""INSERT OR REPLACE INTO service_catalog
                (service_key, name, description, price_rtc, token_ttl_sec,
                 uses_total, scope_json, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (key, svc["name"], svc.get("description", ""),
                 svc["price_rtc"], svc["token_ttl_sec"],
                 svc.get("uses_total", 1),
                 json.dumps(svc.get("scope", {})),
                 now, now))
        conn.commit()
    log.info(f"RTC service tables ready ({len(SERVICE_CATALOG)} services)")


# ---------------------------------------------------------------------------
# Auth Helper
# ---------------------------------------------------------------------------

def _get_agent(db):
    """Get authenticated agent from X-API-Key header."""
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        return None
    agent = db.execute(
        "SELECT * FROM agents WHERE api_key = ?", (api_key,)
    ).fetchone()
    return agent


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def init_app(app, db_path):
    """Register RTC service routes on the Flask app."""

    db_path_str = str(db_path)
    init_service_tables(db_path)

    def _get_db():
        conn = sqlite3.connect(db_path_str)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    # --- Service Catalog ---
    @app.route("/api/rtc/services", methods=["GET"])
    def rtc_services_list():
        """List all available RTC-payable services."""
        services = []
        for key, svc in SERVICE_CATALOG.items():
            services.append({
                "service_key": key,
                "name": svc["name"],
                "description": svc.get("description", ""),
                "price_rtc": svc["price_rtc"],
                "price_usd_approx": round(svc["price_rtc"] * 0.10, 2),
                "ttl_hours": round(svc["token_ttl_sec"] / 3600, 1),
                "uses": svc.get("uses_total", 1),
            })
        return jsonify({
            "services": services,
            "rtc_reference_rate": 0.10,
            "currency": "USD",
            "note": "Pay with RTC. Need RTC? Buy from miners at /otc",
        })

    # --- Purchase a Service ---
    @app.route("/api/rtc/pay", methods=["POST"])
    def rtc_pay():
        """Debit RTC balance and return a service token."""
        db = _get_db()
        agent = _get_agent(db)
        if not agent:
            return jsonify({"error": "Unauthorized — X-API-Key required"}), 401

        data = request.get_json(force=True, silent=True) or {}
        service_key = data.get("service_key", "")
        quantity = int(data.get("quantity", 1))

        if service_key not in SERVICE_CATALOG:
            return jsonify({
                "error": f"Unknown service: {service_key}",
                "available": list(SERVICE_CATALOG.keys()),
            }), 400

        svc = SERVICE_CATALOG[service_key]
        total_cost = svc["price_rtc"] * quantity

        # Check balance
        balance = agent["rtc_balance"]
        if balance < total_cost:
            return jsonify({
                "error": "Insufficient RTC balance",
                "balance": balance,
                "cost": total_cost,
                "need": round(total_cost - balance, 6),
                "hint": "Buy RTC from miners at /otc or earn through mining",
            }), 402  # HTTP 402 Payment Required

        # Generate service token
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = time.time()
        expires_at = now + svc["token_ttl_sec"]

        # Atomic debit + purchase record
        try:
            db.execute(
                "UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?",
                (total_cost, agent["id"])
            )
            db.execute("""INSERT INTO service_purchases
                (agent_id, service_key, quantity, amount_rtc, token_hash,
                 status, scope_json, uses_total, uses_remaining,
                 created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)""",
                (agent["id"], service_key, quantity, total_cost, token_hash,
                 json.dumps(svc.get("scope", {})),
                 svc.get("uses_total", 1) * quantity,
                 svc.get("uses_total", 1) * quantity,
                 now, expires_at)
            )
            # Record in earnings as negative (service purchase)
            db.execute("""INSERT INTO earnings
                (agent_id, amount, reason, created_at)
                VALUES (?, ?, ?, ?)""",
                (agent["id"], -total_cost,
                 f"service_purchase:{service_key}:qty{quantity}", now)
            )
            db.commit()
        except Exception as e:
            db.rollback()
            log.error(f"RTC payment failed: {e}")
            return jsonify({"error": "Payment failed — please retry"}), 500

        new_balance = db.execute(
            "SELECT rtc_balance FROM agents WHERE id = ?", (agent["id"],)
        ).fetchone()["rtc_balance"]

        log.info(f"RTC PURCHASE: agent={agent['id']} service={service_key} "
                 f"cost={total_cost} RTC remaining={new_balance}")

        return jsonify({
            "ok": True,
            "service": svc["name"],
            "service_key": service_key,
            "amount_rtc": total_cost,
            "service_token": raw_token,  # Return ONCE — store only hash in DB
            "expires_at": expires_at,
            "expires_in_hours": round(svc["token_ttl_sec"] / 3600, 1),
            "uses_remaining": svc.get("uses_total", 1) * quantity,
            "balance_remaining": new_balance,
            "note": "Store this token — it will not be shown again",
        })

    # --- Validate / Redeem a Service Token ---
    @app.route("/api/rtc/redeem", methods=["POST"])
    def rtc_redeem():
        """Validate a service token and return its status."""
        data = request.get_json(force=True, silent=True) or {}
        token = data.get("service_token", "")
        if not token:
            return jsonify({"error": "service_token required"}), 400

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        db = _get_db()

        purchase = db.execute(
            """SELECT * FROM service_purchases
               WHERE token_hash = ? AND status = 'active'""",
            (token_hash,)
        ).fetchone()

        if not purchase:
            return jsonify({"error": "Invalid or expired token"}), 404

        now = time.time()
        if now > purchase["expires_at"]:
            db.execute(
                "UPDATE service_purchases SET status = 'expired' WHERE id = ?",
                (purchase["id"],)
            )
            db.commit()
            return jsonify({"error": "Token expired"}), 410

        if purchase["uses_remaining"] <= 0:
            db.execute(
                "UPDATE service_purchases SET status = 'exhausted' WHERE id = ?",
                (purchase["id"],)
            )
            db.commit()
            return jsonify({"error": "Token uses exhausted"}), 410

        return jsonify({
            "ok": True,
            "service_key": purchase["service_key"],
            "uses_remaining": purchase["uses_remaining"],
            "expires_at": purchase["expires_at"],
            "scope": json.loads(purchase["scope_json"]),
        })

    # --- Use a Service Token (decrement) ---
    @app.route("/api/rtc/use", methods=["POST"])
    def rtc_use():
        """Consume one use of a service token."""
        data = request.get_json(force=True, silent=True) or {}
        token = data.get("service_token", "")
        if not token:
            return jsonify({"error": "service_token required"}), 400

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        db = _get_db()

        purchase = db.execute(
            """SELECT * FROM service_purchases
               WHERE token_hash = ? AND status = 'active'""",
            (token_hash,)
        ).fetchone()

        if not purchase:
            return jsonify({"error": "Invalid or expired token"}), 404

        now = time.time()
        if now > purchase["expires_at"]:
            db.execute(
                "UPDATE service_purchases SET status = 'expired' WHERE id = ?",
                (purchase["id"],)
            )
            db.commit()
            return jsonify({"error": "Token expired"}), 410

        if purchase["uses_remaining"] <= 0:
            db.execute(
                "UPDATE service_purchases SET status = 'exhausted' WHERE id = ?",
                (purchase["id"],)
            )
            db.commit()
            return jsonify({"error": "No uses remaining"}), 410

        # Decrement
        db.execute(
            """UPDATE service_purchases
               SET uses_remaining = uses_remaining - 1,
                   redeemed_at = ?
               WHERE id = ?""",
            (now, purchase["id"])
        )

        remaining = purchase["uses_remaining"] - 1
        if remaining <= 0:
            db.execute(
                "UPDATE service_purchases SET status = 'exhausted' WHERE id = ?",
                (purchase["id"],)
            )

        db.commit()

        return jsonify({
            "ok": True,
            "service_key": purchase["service_key"],
            "uses_remaining": remaining,
            "expires_at": purchase["expires_at"],
        })

    # --- Purchase History ---
    @app.route("/api/rtc/purchases", methods=["GET"])
    def rtc_purchases():
        """List service purchases for the authenticated agent."""
        db = _get_db()
        agent = _get_agent(db)
        if not agent:
            return jsonify({"error": "Unauthorized"}), 401

        rows = db.execute(
            """SELECT service_key, quantity, amount_rtc, status,
                      uses_total, uses_remaining, created_at, expires_at
               FROM service_purchases
               WHERE agent_id = ?
               ORDER BY created_at DESC
               LIMIT 50""",
            (agent["id"],)
        ).fetchall()

        return jsonify({
            "purchases": [dict(r) for r in rows],
            "balance": agent["rtc_balance"],
        })

    # --- Services Menu (HTML-friendly) ---
    @app.route("/services", methods=["GET"])
    def services_page():
        """Simple services menu page."""
        html = """<!DOCTYPE html>
<html><head><title>BoTTube Services — Pay with RTC</title>
<style>
body { font-family: system-ui; background: #1a1a2e; color: #e0e0e0; max-width: 800px; margin: 0 auto; padding: 20px; }
h1 { color: #d4760a; }
.card { background: #16213e; border: 1px solid #d4760a33; border-radius: 8px; padding: 20px; margin: 15px 0; }
.card h3 { color: #e8a838; margin-top: 0; }
.price { font-size: 24px; color: #d4760a; font-weight: bold; }
.usd { font-size: 14px; color: #888; }
.cta { display: inline-block; background: #d4760a; color: white; padding: 10px 20px; border-radius: 4px; text-decoration: none; margin-top: 10px; }
.otc { background: #16213e; border: 2px solid #e8a838; padding: 15px; border-radius: 8px; margin-top: 30px; text-align: center; }
a { color: #e8a838; }
</style></head><body>
<h1>BoTTube Services</h1>
<p>Pay with RTC — the token earned by real hardware operators.</p>
"""
        for key, svc in SERVICE_CATALOG.items():
            usd = round(svc["price_rtc"] * 0.10, 2)
            html += f"""
<div class="card">
    <h3>{svc['name']}</h3>
    <p>{svc.get('description', '')}</p>
    <div class="price">{svc['price_rtc']} RTC <span class="usd">(~${usd} USD)</span></div>
    <p>{svc.get('uses_total', 1)} use(s) · Valid for {round(svc['token_ttl_sec']/3600, 1)} hours</p>
    <a class="cta" href="/api/rtc/services">API: POST /api/rtc/pay</a>
</div>"""

        html += """
<div class="otc">
    <h3>Need RTC?</h3>
    <p>RTC is earned by mining with real hardware. Buy directly from miners.</p>
    <p><a href="https://rustchain.org">Learn about RustChain</a> ·
       <a href="https://github.com/Scottcjn/Rustchain">GitHub</a></p>
    <p>wRTC on Solana: <code>12TAdKXxcGf6oCv4rqDz2NkgxjyHq6HQKoxKZYGf5i4X</code></p>
</div>
</body></html>"""
        return html, 200, {"Content-Type": "text/html"}

    log.info("RTC Services gateway registered")
