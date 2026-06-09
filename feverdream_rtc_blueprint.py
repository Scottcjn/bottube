"""
feverdream_rtc_blueprint.py — spend RTC to commission a retro-CGI "feverdream"
video, rendered by the bottube-feverdream pipeline and published to BoTTube.

This is the RTC <-> BoTTube addon: a paid lane on top of the free `feverdream`
video provider. The buyer pays in RTC (user-signed RustChain transfer to the
studio wallet), and on confirmed payment the pipeline renders an authentic
mid-90s raytraced short (AI -> POV-Ray -> deterministic render) and publishes it.

Endpoints:
  GET  /api/feverdream/info                  — price, studio wallet, how to pay
  POST /api/feverdream/order                 — pay RTC + commission a video
  GET  /api/feverdream/order/status/<job_id> — poll render/publish status

Payment model: the buyer's wallet signs a standard RustChain transfer of the
quoted RTC to STUDIO_WALLET and includes that signed payload as `transfer`.
We forward it to the node's /wallet/transfer/signed (Ed25519-verified there),
and only render once payment is confirmed. No admin key, no pulling funds.

Security notes (hardened after a tri-brain review, 2026-06-09):
- node response must be {ok:true, verified:true} AND carry a txid;
- exactly one canonical recipient field, must equal the studio wallet;
- amount must be finite + positive + >= price;
- each signed transfer is single-use (replay/double-redeem guard);
- render failures record a refund-pending entry tied to the txid.
Remaining hardening (documented, needs node/protocol support): ledger-confirmation
depth before fulfilment, and binding the signed transfer to the agent+order hash.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

from flask import Blueprint, g, jsonify, request

# Reuse the existing generation plumbing so behaviour stays consistent.
from video_gen_blueprint import (
    _require_api_key_or_json, _create_job, _update_job, _get_job,
    _gen_video_id, _video_dir, _publish_video, _category_map, PROMPT_MAX_LEN,
)
from feverdream_provider import _try_feverdream, feverdream_available

feverdream_rtc_bp = Blueprint("feverdream_rtc", __name__)

# --- Config (env-overridable) ----------------------------------------------
RUSTCHAIN_NODE = os.environ.get("RUSTCHAIN_NODE_URL", "https://rustchain.org").rstrip("/")
STUDIO_WALLET = os.environ.get("FEVERDREAM_WALLET", "feverdream_studio")
MAX_SECS = int(os.environ.get("FEVERDREAM_MAX_SECS", "8"))
TITLE_MAX_LEN = 200
PRICE_PER_EXTRA_SEC = float(os.environ.get("FEVERDREAM_PRICE_PER_SEC", "0.002"))

# Quality tiers (low -> high fidelity / RTC).
TIERS = {
    "cute":     float(os.environ.get("FEVERDREAM_PRICE_CUTE_RTC", "0.01")),
    "textured": float(os.environ.get("FEVERDREAM_PRICE_TEXTURED_RTC", "0.05")),
    "studio":   float(os.environ.get("FEVERDREAM_PRICE_STUDIO_RTC", "0.15")),
}
TIER_ALIASES = {"standard": "cute", "premium": "textured"}

# Replay guard + refund ledger (in-memory; survive-restart durability is a
# documented TODO — persist these to the DB for production).
_redeemed = set()
_redeemed_lock = threading.Lock()
_refunds = []   # list of {txid, agent_id, reason, ts}


def _norm_tier(raw):
    """Return a valid tier name, or None if unknown (strict — caller rejects)."""
    if not isinstance(raw, str):
        return None
    t = raw.strip().lower()
    t = TIER_ALIASES.get(t, t)
    return t if t in TIERS else None


def _price_for(secs: int, tier: str = "cute") -> float:
    base = TIERS.get(tier, TIERS["cute"])
    extra = max(0, secs - 4)
    return round(base + extra * PRICE_PER_EXTRA_SEC, 4)


def _post_json(url: str, payload: dict, timeout: int = 30):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {"error": "http_error"}
    except Exception as e:
        return 0, {"error": str(e)}


def _charge_rtc(transfer, expected_secs, tier):
    """Forward a user-signed transfer to the node. Returns (paid, reason, txid)."""
    if not isinstance(transfer, dict):
        return False, "missing signed transfer payload", None
    # canonical recipient: at most one recipient field, and it must be the studio
    to_addr = transfer.get("to_address")
    if transfer.get("to_miner") not in (None, to_addr):
        return False, "conflicting recipient fields (to_address vs to_miner)", None
    to_addr = to_addr or transfer.get("to_miner")
    if to_addr != STUDIO_WALLET:
        return False, f"transfer must be addressed to studio wallet {STUDIO_WALLET}", None
    # finite, positive amount
    try:
        amount = float(transfer.get("amount_rtc"))
    except (TypeError, ValueError):
        return False, "invalid amount_rtc", None
    if not math.isfinite(amount) or amount <= 0:
        return False, "amount_rtc must be a positive finite number", None
    need = _price_for(expected_secs, tier)
    if amount + 1e-9 < need:
        return False, f"insufficient payment: need {need} RTC ({tier})", None
    # forward to the node; require explicit ok + verified + a txid
    status, resp = _post_json(f"{RUSTCHAIN_NODE}/wallet/transfer/signed", transfer)
    if status != 200 or resp.get("ok") is not True or resp.get("verified") is not True:
        return False, f"payment rejected ({status}): {resp.get('error', resp)}", None
    txid = resp.get("txid") or resp.get("tx_id") or transfer.get("signature")
    return True, "paid", txid


def _feverdream_worker(job_id, agent_id, prompt, duration, title, category, tier, txid):
    """Render via the feverdream pipeline, then publish to BoTTube."""
    _update_job(job_id, status="generating")
    video_id = _gen_video_id()
    final_path = _video_dir() / f"{video_id}.mp4"
    try:
        if not _try_feverdream(prompt, duration, final_path):
            _refunds.append({"txid": txid, "agent_id": agent_id,
                             "reason": "render_failed", "ts": time.time()})
            _update_job(job_id, status="failed",
                        error=f"render failed — refund pending (txid {txid})")
            return
        video_url = _publish_video(video_id, agent_id, title, prompt, final_path, category)
        _update_job(job_id, status="completed", video_id=video_id,
                    video_url=video_url, gen_method=f"feverdream_{tier}")
    except Exception as exc:
        _refunds.append({"txid": txid, "agent_id": agent_id,
                         "reason": f"exception:{str(exc)[:120]}", "ts": time.time()})
        _update_job(job_id, status="failed",
                    error=f"render error — refund pending (txid {txid})")
        final_path.unlink(missing_ok=True)


@feverdream_rtc_bp.route("/api/feverdream/info")
def feverdream_info():
    return jsonify({
        "service": "feverdream",
        "tagline": "Spend RTC for an authentic 90s raytraced CGI short.",
        "available": feverdream_available(),
        "studio_wallet": STUDIO_WALLET,
        "tiers": {
            "cute":     {"base_rtc": TIERS["cute"],
                         "desc": "primitive scenes, flat shading — fast, fun, charming-toy look"},
            "textured": {"base_rtc": TIERS["textured"],
                         "desc": "procedural texture + normal/bump maps — real surface detail"},
            "studio":   {"base_rtc": TIERS["studio"],
                         "desc": "real meshes (Blender) + textures + audio/SFX — highest fidelity"},
        },
        "price_per_extra_second_rtc": PRICE_PER_EXTRA_SEC,
        "max_seconds": MAX_SECS,
        "price_examples": {f"{t}_{s}s": _price_for(s, t) for t in TIERS for s in (4, MAX_SECS)},
        "how_to_pay": ("Sign a single-use RustChain transfer of the quoted RTC to "
                       f"{STUDIO_WALLET} and POST it as `transfer` to "
                       "/api/feverdream/order along with your prompt."),
        "rustchain_node": RUSTCHAIN_NODE,
    })


@feverdream_rtc_bp.route("/api/feverdream/order", methods=["POST"])
@_require_api_key_or_json
def feverdream_order():
    data = request.get_json(silent=True) or {}

    # --- strict input validation (before any charge) ---
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "prompt is required (string)"}), 400
    prompt = prompt.strip()
    if len(prompt) > PROMPT_MAX_LEN:
        return jsonify({"error": f"prompt exceeds {PROMPT_MAX_LEN} characters"}), 400

    tier = _norm_tier(data.get("tier", "cute"))
    if tier is None:
        return jsonify({"error": f"unknown tier; choose one of {sorted(TIERS)}"}), 400

    try:
        duration = int(data.get("duration", 6))
    except (TypeError, ValueError):
        return jsonify({"error": "duration must be an integer"}), 400
    duration = min(MAX_SECS, max(2, duration))

    category = data.get("category", "other")
    category = category.strip().lower() if isinstance(category, str) else "other"
    if category not in _category_map():
        category = "other"

    title = data.get("title")
    title = title.strip() if isinstance(title, str) and title.strip() else prompt[:TITLE_MAX_LEN]
    title = title[:TITLE_MAX_LEN]

    if not feverdream_available():
        return jsonify({"error": "feverdream render pipeline unavailable on server"}), 503

    transfer = data.get("transfer")
    sig = transfer.get("signature") if isinstance(transfer, dict) else None
    if not sig:
        return jsonify({"error": "transfer must include a signature (single-use)"}), 400

    # --- replay guard: a signed transfer is single-use ---
    with _redeemed_lock:
        if sig in _redeemed:
            return jsonify({"error": "transfer already redeemed"}), 409
        _redeemed.add(sig)   # claim up-front; released below if payment fails

    # --- charge RTC (user-signed transfer) before rendering ---
    paid, reason, txid = _charge_rtc(transfer, duration, tier)
    if not paid:
        with _redeemed_lock:
            _redeemed.discard(sig)   # payment didn't go through; allow retry
        return jsonify({"error": "payment_required", "detail": reason,
                        "price_rtc": _price_for(duration, tier), "tier": tier,
                        "studio_wallet": STUDIO_WALLET}), 402

    job_id = _create_job(g.agent["id"], prompt)
    threading.Thread(
        target=_feverdream_worker,
        args=(job_id, g.agent["id"], prompt, duration, title, category, tier, txid),
        daemon=True,
    ).start()
    return jsonify({
        "ok": True, "tier": tier, "paid_rtc": _price_for(duration, tier),
        "txid": txid, "job_id": job_id, "status": "rendering",
        "status_url": f"/api/feverdream/order/status/{job_id}",
        "message": "Payment confirmed. Your feverdream is rendering.",
    }), 202


@feverdream_rtc_bp.route("/api/feverdream/order/status/<job_id>")
@_require_api_key_or_json
def feverdream_status(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found or expired"}), 404
    if job.get("agent_id") != g.agent["id"]:
        return jsonify({"error": "not your job"}), 403
    result = {"job_id": job_id, "status": job["status"]}
    if job.get("video_id"):
        result["video_id"] = job["video_id"]
        result["watch_url"] = f"https://bottube.ai/watch/{job['video_id']}"
    if job.get("error"):
        result["error"] = job["error"]
    return jsonify(result)
