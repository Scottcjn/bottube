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
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
from flask import Blueprint, jsonify, request

pi_pay_bp = Blueprint("pi_pay", __name__)

PI_API_KEY = os.environ.get("PI_API_KEY", "")
PI_SANDBOX = os.environ.get("PI_SANDBOX", "1") != "0"   # default Testnet/sandbox
PI_API_BASE = "https://api.minepi.com/v2"
PI_TIMEOUT = float(os.environ.get("PI_TIMEOUT", "15"))
AMOUNT_TOL = 1e-7
_PI_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

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
    """Resolve the sqlite DB path, matching bottube_server.py unless overridden by env."""
    # Default matches bottube_server.py (BASE_DIR/bottube.db); env can override.
    base = os.environ.get("BOTTUBE_BASE_DIR", str(Path(__file__).resolve().parent))
    return os.environ.get("BOTTUBE_DB_PATH", str(Path(base) / "bottube.db"))


def _conn():
    """Open a sqlite connection to the payments DB with a generous busy timeout."""
    c = sqlite3.connect(_db_path(), timeout=30)
    c.execute("PRAGMA busy_timeout=30000")
    return c


def init_pi_payment_tables(db_path: str = None):
    """Create the pi_payments table if it doesn't already exist."""
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
    """Build the auth headers required by the Pi Platform API."""
    return {"Authorization": f"Key {PI_API_KEY}", "Content-Type": "application/json"}


def _is_valid_pi_identifier(value: str) -> bool:
    """Validate Pi payment IDs and txids against strict path-safe characters."""
    return isinstance(value, str) and bool(_PI_IDENTIFIER_RE.fullmatch(value))


def _pi_get_payment(payment_id: str):
    """Fetch the authoritative payment record from the Pi API."""
    if not _is_valid_pi_identifier(payment_id):
        raise ValueError("invalid payment_id format")
    safe_payment_id = quote(payment_id, safe="")
    r = requests.get(f"{PI_API_BASE}/payments/{safe_payment_id}",
                     headers=_pi_headers(), timeout=PI_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _parse_pi_amount(raw_amount):
    """Parse a finite non-boolean numeric Pi amount, or return None."""
    if isinstance(raw_amount, bool) or raw_amount is None:
        return None
    try:
        amount = float(raw_amount)
    except (TypeError, ValueError):
        return None
    return amount if math.isfinite(amount) else None


def _verify_against_products(p: dict, expected_payment_id: Optional[str] = None):
    """Check a Pi payment's product+amount against PI_PRODUCTS; return (product, amount) or (None, reason)."""
    if not isinstance(p, dict):
        return None, "invalid payment payload"
    identifier = p.get("identifier")
    if expected_payment_id and isinstance(identifier, str) and identifier and identifier != expected_payment_id:
        return None, "payment_id mismatch"
    status_obj = p.get("status")
    if isinstance(status_obj, dict) and (
        status_obj.get("cancelled") is True or status_obj.get("user_cancelled") is True
    ):
        return None, "payment cancelled"
    metadata = p.get("metadata")
    if not isinstance(metadata, dict):
        return None, "missing metadata"
    product = metadata.get("product", "")
    if not isinstance(product, str) or product not in PI_PRODUCTS:
        return None, "unknown product"
    exp = PI_PRODUCTS[product]
    amount = _parse_pi_amount(p.get("amount"))
    if amount is None:
        return None, "invalid amount"
    if not math.isclose(amount, float(exp["pi"]), abs_tol=AMOUNT_TOL):
        return None, "amount mismatch"
    return product, amount


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
    """Report Pi integration config status, active network, and server-authoritative prices."""
    return jsonify({
        "ok": True,
        "configured": bool(PI_API_KEY),
        "network": "testnet/sandbox" if PI_SANDBOX else "mainnet",
        "sandbox": PI_SANDBOX,
        "products": {k: v["pi"] for k, v in PI_PRODUCTS.items()},
    })


def _optional_str_field(data, name):
    """Return ``data[name]`` stripped, ``""`` if absent/null, or ``None`` if it is not a string."""
    value = data.get(name)
    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    return value.strip()


def _parse_pi_json_body():
    """Verify PI_API_KEY configuration and parse a JSON object body."""
    if not PI_API_KEY:
        return None, (jsonify({"error": "Pi not configured (PI_API_KEY unset)"}), 503)
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, (jsonify({"error": "JSON body must be an object"}), 400)
    return data, None


def _lookup_and_verify_payment(payment_id: str, action: str):
    """Fetch a Pi payment and verify product, amount, and fulfillment readiness."""
    try:
        p = _pi_get_payment(payment_id)
    except (requests.RequestException, ValueError) as e:
        print(f"[pi] lookup failed: {e}", flush=True)
        return None, None, None, (jsonify({"error": "Pi lookup failed, try again"}), 502)
    product, amount = _verify_against_products(p, expected_payment_id=payment_id)
    if product is None:
        return None, None, None, (jsonify({"error": f"refusing to {action}: {amount}"}), 400)
    if product not in IMPLEMENTED_GRANTS:
        # Never take a payment we cannot fulfill.
        return None, None, None, (
            jsonify({"error": "fulfillment for this product is not enabled yet", "product": product}),
            503,
        )
    return p, product, amount, None


def _pi_user_uid(payment: dict) -> str:
    """Safely extract user_uid as a string."""
    raw = payment.get("user_uid")
    return raw if isinstance(raw, str) else ""


@pi_pay_bp.route("/pi/approve", methods=["POST"])
def pi_approve():
    """Server-side approval leg: re-verify the payment against Pi and our product table, then call Pi /approve."""
    data, err = _parse_pi_json_body()
    if err:
        return err
    payment_id = _optional_str_field(data, "payment_id")
    if payment_id is None:
        return jsonify({"error": "payment_id must be a string"}), 400
    if not payment_id:
        return jsonify({"error": "payment_id required"}), 400
    if not _is_valid_pi_identifier(payment_id):
        return jsonify({"error": "invalid payment_id format"}), 400

    p, product, amount, err = _lookup_and_verify_payment(payment_id, "approve")
    if err:
        return err

    safe_payment_id = quote(payment_id, safe="")
    conn = _conn()
    try:
        now = time.time()
        conn.execute(
            "INSERT OR IGNORE INTO pi_payments (payment_id, pi_uid, product, amount_pi, status, created_at, updated_at) "
            "VALUES (?,?,?,?, 'created', ?, ?)",
            (payment_id, _pi_user_uid(p), product, amount, now, now))
        conn.commit()
        existing = conn.execute(
            "SELECT status FROM pi_payments WHERE payment_id=?", (payment_id,)
        ).fetchone()
        if existing and existing[0] in ("completing", "completed"):
            return jsonify({
                "error": "payment already completed",
                "payment_id": payment_id,
                "status": existing[0],
            }), 409
        r = requests.post(f"{PI_API_BASE}/payments/{safe_payment_id}/approve",
                          headers=_pi_headers(), timeout=PI_TIMEOUT)
        if r.status_code >= 300:
            print(f"[pi] approve rejected by upstream: status={r.status_code}", flush=True)
            return jsonify({"error": "pi approve failed"}), 502
        conn.execute(
            "UPDATE pi_payments SET status='approved', updated_at=? "
            "WHERE payment_id=? AND status='created'",
            (time.time(), payment_id),
        )
        conn.commit()
    except requests.RequestException as e:
        print(f"[pi] approve error: {e}", flush=True)
        return jsonify({"error": "Pi approve failed, try again"}), 502
    finally:
        conn.close()
    return jsonify({"ok": True, "payment_id": payment_id, "status": "approved"})


def _pi_complete_already_claimed_response(conn, payment_id: str):
    """Report current payment state when another request already claimed completion."""
    row = conn.execute(
        "SELECT status, granted FROM pi_payments WHERE payment_id=?", (payment_id,)
    ).fetchone()
    if row and row[0] == "completed" and row[1] == 1:
        return jsonify({"ok": True, "payment_id": payment_id, "status": "completed", "duplicate": True})
    return jsonify({
        "ok": False,
        "payment_id": payment_id,
        "status": (row[0] if row else "unknown"),
        "pending": True,
        "note": "completion in progress; retry shortly",
    }), 202


def _parse_pi_complete_identifiers(data: dict):
    """Extract and validate payment_id and txid from /pi/complete payload."""
    payment_id = _optional_str_field(data, "payment_id")
    txid = _optional_str_field(data, "txid")
    if payment_id is None or txid is None:
        return None, None, (jsonify({"error": "payment_id and txid must be strings"}), 400)
    if not payment_id or not txid:
        return None, None, (jsonify({"error": "payment_id and txid required"}), 400)
    if not _is_valid_pi_identifier(payment_id) or not _is_valid_pi_identifier(txid):
        return None, None, (jsonify({"error": "invalid payment_id or txid format"}), 400)
    return payment_id, txid, None


@pi_pay_bp.route("/pi/complete", methods=["POST"])
def pi_complete():
    """Server-side completion leg: re-verify, call Pi /complete, then grant the entitlement idempotently."""
    data, err = _parse_pi_json_body()
    if err:
        return err
    payment_id, txid, err = _parse_pi_complete_identifiers(data)
    if err:
        return err

    p, product, amount, err = _lookup_and_verify_payment(payment_id, "complete")
    if err:
        return err

    safe_payment_id = quote(payment_id, safe="")
    user_uid = _pi_user_uid(p)
    conn = _conn()
    try:
        now = time.time()
        conn.execute(
            "INSERT OR IGNORE INTO pi_payments (payment_id, pi_uid, product, amount_pi, status, created_at, updated_at) "
            "VALUES (?,?,?,?, 'approved', ?, ?)",
            (payment_id, user_uid, product, amount, now, now))
        cur = conn.execute(
            "UPDATE pi_payments SET status='completing', txid=?, updated_at=? "
            "WHERE payment_id=? AND status IN ('created','approved')",
            (txid, now, payment_id))
        conn.commit()
        if cur.rowcount == 0:
            return _pi_complete_already_claimed_response(conn, payment_id)

        r = requests.post(f"{PI_API_BASE}/payments/{safe_payment_id}/complete",
                          headers=_pi_headers(), json={"txid": txid}, timeout=PI_TIMEOUT)
        if r.status_code >= 300:
            conn.execute(
                "UPDATE pi_payments SET status='approved', updated_at=? "
                "WHERE payment_id=? AND status='completing'",
                (time.time(), payment_id),
            )
            conn.commit()
            print(f"[pi] complete rejected by upstream: status={r.status_code}", flush=True)
            return jsonify({"error": "pi complete failed"}), 502

        ok = _grant_entitlement(user_uid, product, payment_id)
        conn.execute(
            "UPDATE pi_payments SET status='completed', granted=?, updated_at=? WHERE payment_id=?",
            (1 if ok else 0, time.time(), payment_id))
        conn.commit()
        if not ok:
            return jsonify({"error": "payment settled but entitlement failed; will reconcile",
                            "payment_id": payment_id, "status": "completed_ungranted"}), 500
    except requests.RequestException as e:
        # The row was already claimed as ``completing`` before the remote
        # request.  Release that claim on transport failure so the client's
        # retry can actually resume instead of returning 202 forever.
        conn.execute(
            "UPDATE pi_payments SET status='approved', updated_at=? "
            "WHERE payment_id=? AND status='completing'",
            (time.time(), payment_id),
        )
        conn.commit()
        print(f"[pi] complete error: {e}", flush=True)
        return jsonify({"error": "Pi complete failed, try again"}), 502
    finally:
        conn.close()
    return jsonify({"ok": True, "payment_id": payment_id, "status": "completed"})
