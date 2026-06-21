# SPDX-License-Identifier: Apache-2.0
# Author: @Scottcjn (Elyan Labs)
"""
Pi Network PAYMENT routes for BoTTube (testnet/sandbox by default).

Auth (/pi/auth) lives in bottube_server.py already — this module adds ONLY the
payment legs so it can never collide with the existing /pi/auth endpoint:

  frontend Pi.createPayment(...) -> onReadyForServerApproval(paymentId)
      -> POST /pi/approve  {payment_id}        -> verify amount, call Pi /approve
  Pi proceeds                    -> onReadyForServerCompletion(paymentId, txid)
      -> POST /pi/complete {payment_id, txid}  -> re-verify, call Pi /complete, grant

Security posture (do NOT weaken):
- PI_API_KEY from env; never hardcoded. Server is the source of truth for price:
  both approve AND complete re-fetch the payment from Pi and verify product+amount.
- Granting is atomic & idempotent (single UPDATE ... WHERE status IN (...) claims it).
- Resume-safe: /pi/complete reconstructs state from Pi if no local row exists.
- Testnet (sandbox) by default; flip PI_SANDBOX=0 only against the Mainnet app.
"""
import math
import os
import sqlite3
import time
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request

pi_pay_bp = Blueprint("pi_pay", __name__)

PI_API_KEY = os.environ.get("PI_API_KEY", "")
PI_SANDBOX = os.environ.get("PI_SANDBOX", "1") != "0"   # default Testnet/sandbox
PI_API_BASE = "https://api.minepi.com/v2"
PI_TIMEOUT = float(os.environ.get("PI_TIMEOUT", "15"))
AMOUNT_TOL = 1e-7

# Server-authoritative prices. Frontend reads these via /pi/health.
PI_PRODUCTS = {
    "test_payment":       {"pi": 0.1, "grants": "test"},               # checklist test tx
    "video_text_card":    {"pi": 0.25, "grants": "gen_text_card"},
    "video_ken_burns":    {"pi": 1.0, "grants": "gen_ken_burns"},
    "video_full_ai":      {"pi": 3.0, "grants": "gen_full_ai"},
    "premium_generation": {"pi": 1.0, "grants": "premium_gen_credit"},
    "boost":              {"pi": 2.0, "grants": "feature_boost"},
}

# Products whose fulfillment is actually wired in _grant_entitlement(). We REFUSE to
# approve/complete any other product so a payment is never taken without delivery.
# Add video_* / premium_* / boost here only once their entitlement is implemented.
IMPLEMENTED_GRANTS = {"test_payment"}


def _db_path() -> str:
    # Default matches bottube_server.py (BASE_DIR/bottube.db); env can override.
    base = os.environ.get("BOTTUBE_BASE_DIR", str(Path(__file__).resolve().parent))
    return os.environ.get("BOTTUBE_DB_PATH", str(Path(base) / "bottube.db"))


def _conn():
    c = sqlite3.connect(_db_path(), timeout=30)
    c.execute("PRAGMA busy_timeout=30000")
    return c


def init_pi_payment_tables(db_path: str = None):
    path = db_path or _db_path()
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_payments (
                payment_id  TEXT PRIMARY KEY,
                pi_uid      TEXT,
                product     TEXT,
                amount_pi   REAL,
                status      TEXT NOT NULL DEFAULT 'created',
                txid        TEXT DEFAULT '',
                granted     INTEGER NOT NULL DEFAULT 0,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _pi_headers():
    return {"Authorization": f"Key {PI_API_KEY}", "Content-Type": "application/json"}


def _pi_get_payment(payment_id: str):
    r = requests.get(f"{PI_API_BASE}/payments/{payment_id}",
                     headers=_pi_headers(), timeout=PI_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _verify_against_products(p: dict):
    product = (p.get("metadata") or {}).get("product", "")
    exp = PI_PRODUCTS.get(product)
    if not exp:
        return None, f"unknown product: {product!r}"
    if not math.isclose(float(p.get("amount", 0)), float(exp["pi"]), abs_tol=AMOUNT_TOL):
        return None, "amount mismatch"
    return product, float(p.get("amount", 0))


def _grant_entitlement(pi_uid: str, product: str, payment_id: str) -> bool:
    """Grant the purchased product. MUST be idempotent and return True on success.
    Only IMPLEMENTED_GRANTS products reach here (approve/complete refuse the rest),
    so this never silently 'succeeds' for an unwired product."""
    if product == "test_payment":
        return True  # checklist test tx — no entitlement to deliver
    # TODO: enqueue LTX generation / credit grant (idempotent by payment_id), then add
    # the product key to IMPLEMENTED_GRANTS.
    return False


@pi_pay_bp.route("/pi/health", methods=["GET"])
def pi_health():
    return jsonify({
        "ok": True,
        "configured": bool(PI_API_KEY),
        "network": "testnet/sandbox" if PI_SANDBOX else "mainnet",
        "sandbox": PI_SANDBOX,
        "products": {k: v["pi"] for k, v in PI_PRODUCTS.items()},
    })


@pi_pay_bp.route("/pi/approve", methods=["POST"])
def pi_approve():
    if not PI_API_KEY:
        return jsonify({"error": "Pi not configured (PI_API_KEY unset)"}), 503
    payment_id = ((request.get_json(silent=True) or {}).get("payment_id") or "").strip()
    if not payment_id:
        return jsonify({"error": "payment_id required"}), 400
    try:
        p = _pi_get_payment(payment_id)
    except requests.RequestException as e:
        return jsonify({"error": f"pi lookup failed: {e}"}), 502
    product, amount = _verify_against_products(p)
    if product is None:
        return jsonify({"error": f"refusing to approve: {amount}"}), 400
    if product not in IMPLEMENTED_GRANTS:
        # Never take a payment we cannot fulfill.
        return jsonify({"error": "fulfillment for this product is not enabled yet",
                        "product": product}), 503

    conn = _conn()
    try:
        now = time.time()
        conn.execute(
            "INSERT OR IGNORE INTO pi_payments (payment_id, pi_uid, product, amount_pi, status, created_at, updated_at) "
            "VALUES (?,?,?,?, 'created', ?, ?)",
            (payment_id, p.get("user_uid", ""), product, amount, now, now))
        conn.commit()
        r = requests.post(f"{PI_API_BASE}/payments/{payment_id}/approve",
                          headers=_pi_headers(), timeout=PI_TIMEOUT)
        if r.status_code >= 300:
            return jsonify({"error": "pi approve failed", "detail": r.text[:200]}), 502
        conn.execute("UPDATE pi_payments SET status='approved', updated_at=? WHERE payment_id=?",
                     (time.time(), payment_id))
        conn.commit()
    except requests.RequestException as e:
        return jsonify({"error": f"pi approve error: {e}"}), 502
    finally:
        conn.close()
    return jsonify({"ok": True, "payment_id": payment_id, "status": "approved"})


@pi_pay_bp.route("/pi/complete", methods=["POST"])
def pi_complete():
    if not PI_API_KEY:
        return jsonify({"error": "Pi not configured (PI_API_KEY unset)"}), 503
    data = request.get_json(silent=True) or {}
    payment_id = (data.get("payment_id") or "").strip()
    txid = (data.get("txid") or "").strip()
    if not payment_id or not txid:
        return jsonify({"error": "payment_id and txid required"}), 400

    try:
        p = _pi_get_payment(payment_id)
    except requests.RequestException as e:
        return jsonify({"error": f"pi lookup failed: {e}"}), 502
    product, amount = _verify_against_products(p)
    if product is None:
        return jsonify({"error": f"refusing to complete: {amount}"}), 400
    if product not in IMPLEMENTED_GRANTS:
        return jsonify({"error": "fulfillment for this product is not enabled yet",
                        "product": product}), 503

    conn = _conn()
    try:
        now = time.time()
        conn.execute(
            "INSERT OR IGNORE INTO pi_payments (payment_id, pi_uid, product, amount_pi, status, created_at, updated_at) "
            "VALUES (?,?,?,?, 'approved', ?, ?)",
            (payment_id, p.get("user_uid", ""), product, amount, now, now))
        cur = conn.execute(
            "UPDATE pi_payments SET status='completing', txid=?, updated_at=? "
            "WHERE payment_id=? AND status IN ('created','approved')",
            (txid, now, payment_id))
        conn.commit()
        if cur.rowcount == 0:
            # Someone else already moved it past created/approved. Report the TRUE state
            # instead of a blanket success: only claim success if actually granted; a row
            # stuck in 'completing' (crash mid-flight) is pending reconciliation, not done.
            row = conn.execute(
                "SELECT status, granted FROM pi_payments WHERE payment_id=?", (payment_id,)
            ).fetchone()
            if row and row[0] == "completed" and row[1] == 1:
                return jsonify({"ok": True, "payment_id": payment_id, "status": "completed", "duplicate": True})
            return jsonify({"ok": False, "payment_id": payment_id,
                            "status": (row[0] if row else "unknown"),
                            "pending": True, "note": "completion in progress; retry shortly"}), 202

        r = requests.post(f"{PI_API_BASE}/payments/{payment_id}/complete",
                          headers=_pi_headers(), json={"txid": txid}, timeout=PI_TIMEOUT)
        if r.status_code >= 300:
            conn.execute("UPDATE pi_payments SET status='approved', updated_at=? WHERE payment_id=?",
                         (time.time(), payment_id))
            conn.commit()
            return jsonify({"error": "pi complete failed", "detail": r.text[:200]}), 502

        ok = _grant_entitlement(p.get("user_uid", ""), product, payment_id)
        conn.execute(
            "UPDATE pi_payments SET status='completed', granted=?, updated_at=? WHERE payment_id=?",
            (1 if ok else 0, time.time(), payment_id))
        conn.commit()
        if not ok:
            return jsonify({"error": "payment settled but entitlement failed; will reconcile",
                            "payment_id": payment_id, "status": "completed_ungranted"}), 500
    except requests.RequestException as e:
        return jsonify({"error": f"pi complete error: {e}"}), 502
    finally:
        conn.close()
    return jsonify({"ok": True, "payment_id": payment_id, "status": "completed"})
