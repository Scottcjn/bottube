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

Payment model: the buyer's wallet signs a standard RustChain transfer of
PRICE_RTC to STUDIO_WALLET and includes that signed payload as `transfer`.
We forward it to the node's /wallet/transfer/signed (Ed25519-verified there),
and only render once payment is confirmed. No admin key, no pulling funds —
the user authorizes their own spend.
"""
from __future__ import annotations

import json
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
PRICE_RTC = float(os.environ.get("FEVERDREAM_PRICE_RTC", "0.01"))
MAX_SECS = int(os.environ.get("FEVERDREAM_MAX_SECS", "8"))
# Tiered pricing: longer clips cost a touch more RTC (still pennies).
PRICE_PER_EXTRA_SEC = float(os.environ.get("FEVERDREAM_PRICE_PER_SEC", "0.002"))


def _price_for(secs: int) -> float:
    extra = max(0, secs - 4)
    return round(PRICE_RTC + extra * PRICE_PER_EXTRA_SEC, 4)


def _post_json(url: str, payload: dict, timeout: int = 30) -> tuple[int, dict]:
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


def _charge_rtc(transfer: dict, expected_secs: int) -> tuple[bool, str]:
    """Forward a user-signed transfer to the node. Returns (paid, reason)."""
    if not isinstance(transfer, dict):
        return False, "missing signed transfer payload"
    to_addr = transfer.get("to_address") or transfer.get("to_miner")
    amount = float(transfer.get("amount_rtc", 0) or 0)
    if to_addr != STUDIO_WALLET:
        return False, f"transfer must be addressed to studio wallet {STUDIO_WALLET}"
    if amount + 1e-9 < _price_for(expected_secs):
        return False, f"insufficient payment: need {_price_for(expected_secs)} RTC"
    status, resp = _post_json(f"{RUSTCHAIN_NODE}/wallet/transfer/signed", transfer)
    if status == 200 and resp.get("ok") and resp.get("verified", True):
        return True, "paid"
    return False, f"payment rejected ({status}): {resp.get('error', resp)}"


def _feverdream_worker(job_id: str, agent_id: int, prompt: str,
                       duration: int, title: str, category: str):
    """Render via the feverdream pipeline, then publish to BoTTube."""
    _update_job(job_id, status="generating")
    video_id = _gen_video_id()
    final_path = _video_dir() / f"{video_id}.mp4"
    try:
        if not _try_feverdream(prompt, duration, final_path):
            _update_job(job_id, status="failed",
                        error="feverdream render failed (payment captured — refund queued)")
            return
        video_url = _publish_video(video_id, agent_id, title, prompt,
                                   final_path, category)
        _update_job(job_id, status="completed", video_id=video_id,
                    video_url=video_url, gen_method="feverdream_rtc")
    except Exception as exc:
        _update_job(job_id, status="failed", error=str(exc)[:500])
        final_path.unlink(missing_ok=True)


@feverdream_rtc_bp.route("/api/feverdream/info")
def feverdream_info():
    return jsonify({
        "service": "feverdream",
        "tagline": "Spend RTC for an authentic 90s raytraced CGI short.",
        "available": feverdream_available(),
        "studio_wallet": STUDIO_WALLET,
        "base_price_rtc": PRICE_RTC,
        "price_per_extra_second_rtc": PRICE_PER_EXTRA_SEC,
        "max_seconds": MAX_SECS,
        "price_examples": {f"{s}s": _price_for(s) for s in (4, 6, MAX_SECS)},
        "how_to_pay": ("Sign a RustChain transfer of the quoted RTC to "
                       f"{STUDIO_WALLET} and POST it as `transfer` to "
                       "/api/feverdream/order along with your prompt."),
        "rustchain_node": RUSTCHAIN_NODE,
    })


@feverdream_rtc_bp.route("/api/feverdream/order", methods=["POST"])
@_require_api_key_or_json
def feverdream_order():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400
    if len(prompt) > PROMPT_MAX_LEN:
        return jsonify({"error": f"prompt exceeds {PROMPT_MAX_LEN} characters"}), 400
    if not feverdream_available():
        return jsonify({"error": "feverdream render pipeline unavailable on server"}), 503

    duration = min(MAX_SECS, max(2, int(data.get("duration", 6))))
    category = (data.get("category") or "other").strip().lower()
    if category not in _category_map():
        category = "other"
    title = (data.get("title") or prompt[:200]).strip()

    # --- charge RTC (user-signed transfer) before rendering ---
    paid, reason = _charge_rtc(data.get("transfer"), duration)
    if not paid:
        return jsonify({"error": "payment_required", "detail": reason,
                        "price_rtc": _price_for(duration),
                        "studio_wallet": STUDIO_WALLET}), 402

    job_id = _create_job(g.agent["id"], prompt)
    threading.Thread(
        target=_feverdream_worker,
        args=(job_id, g.agent["id"], prompt, duration, title, category),
        daemon=True,
    ).start()
    return jsonify({
        "ok": True,
        "paid_rtc": _price_for(duration),
        "job_id": job_id,
        "status": "rendering",
        "status_url": f"/api/feverdream/order/status/{job_id}",
        "message": "Payment confirmed. Your feverdream is rendering.",
    }), 202


@feverdream_rtc_bp.route("/api/feverdream/order/status/<job_id>")
def feverdream_status(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found or expired"}), 404
    result = {"job_id": job_id, "status": job["status"]}
    if job.get("video_id"):
        result["video_id"] = job["video_id"]
        result["watch_url"] = f"https://bottube.ai/watch/{job['video_id']}"
    if job.get("error"):
        result["error"] = job["error"]
    return jsonify(result)
