# SPDX-License-Identifier: Apache-2.0
# Author: @Scottcjn (Elyan Labs)
"""
BoTTube Studio — pay RTC to generate a video. Technical demo of the pay-to-generate
flow on RustChain's own RTC token (no external gatekeeper, ships today). The GENERATION
layer is pluggable: today it uses the existing /api/generate-video cascade
(LTX -> Ken Burns -> ffmpeg); when the Alibaba Cloud video API + SDK arrive, Alibaba
slots into that cascade (video_providers.py) with NO change to this Studio code — the
currency + UI here stay identical.

Endpoints:
  GET  /studio                  -> the Studio storefront page
  GET  /api/studio/info         -> tiers + caller's RTC balance
  POST /api/studio/generate     -> {prompt, tier} : atomic RTC debit + start generation

RTC debit is atomic (conditional UPDATE ... WHERE rtc_balance >= cost) and refunds if
the generation fails to start.
"""
import os
import sqlite3
import threading
import time
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

studio_bp = Blueprint("studio", __name__)

# RTC price per tier (env-overridable). Demo defaults; tune freely.
STUDIO_TIERS = {
    "text_card": {"rtc": float(os.environ.get("STUDIO_RTC_TEXT", "1")),
                  "name": "Text Card", "desc": "Instant title-card video", "badge": "CHEAPEST", "duration": 5},
    "ken_burns": {"rtc": float(os.environ.get("STUDIO_RTC_KENBURNS", "3")),
                  "name": "Ken Burns", "desc": "Cinematic pan & zoom over images", "badge": "POPULAR", "duration": 8},
    "full_ai":   {"rtc": float(os.environ.get("STUDIO_RTC_FULLAI", "5")),
                  "name": "Full AI Video", "desc": "LTX-2 generated, with audio", "badge": "PREMIUM", "duration": 8},
}
PROMPT_MAX = 500
_rate = {}
_COOLDOWN = float(os.environ.get("STUDIO_COOLDOWN", "30"))  # per-caller, protects the GPU


def _db_path() -> str:
    base = os.environ.get("BOTTUBE_BASE_DIR", str(Path(__file__).resolve().parent))
    return os.environ.get("BOTTUBE_DB_PATH", str(Path(base) / "bottube.db"))


def _conn():
    c = sqlite3.connect(_db_path(), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    return c


def _resolve_caller(conn):
    """(id, agent_name, rtc_balance) for an API agent (X-API-Key/agent_api_key) or a
    logged-in human (session), else None."""
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        api_key = ((request.get_json(silent=True) or {}).get("agent_api_key") or "").strip()
    if api_key:
        row = conn.execute(
            "SELECT id, agent_name, rtc_balance FROM agents WHERE api_key=? AND COALESCE(is_banned,0)=0",
            (api_key,)).fetchone()
        if row:
            return row
    uid = session.get("user_id")
    if uid:
        row = conn.execute(
            "SELECT id, agent_name, rtc_balance FROM agents WHERE id=? AND COALESCE(is_banned,0)=0",
            (uid,)).fetchone()
        if row:
            return row
    return None


@studio_bp.route("/studio")
def studio_home():
    tiers = [{"key": k, **v} for k, v in STUDIO_TIERS.items()]
    return render_template("studio.html", studio_tiers=tiers)


@studio_bp.route("/api/studio/info", methods=["GET"])
def studio_info():
    conn = _conn()
    try:
        caller = _resolve_caller(conn)
        bal = round(caller["rtc_balance"], 6) if caller else None
        signed_in = caller is not None
    finally:
        conn.close()
    return jsonify({
        "ok": True,
        "signed_in": signed_in,
        "rtc_balance": bal,
        "tiers": {k: v["rtc"] for k, v in STUDIO_TIERS.items()},
    })


@studio_bp.route("/api/studio/generate", methods=["POST"])
def studio_generate():
    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    tier = (body.get("tier") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    if len(prompt) > PROMPT_MAX:
        return jsonify({"error": f"prompt exceeds {PROMPT_MAX} characters"}), 400
    if tier not in STUDIO_TIERS:
        return jsonify({"error": "unknown tier"}), 400
    cost = STUDIO_TIERS[tier]["rtc"]

    conn = _conn()
    try:
        caller = _resolve_caller(conn)
        if not caller:
            return jsonify({"error": "sign in (or use an API key) to generate"}), 401
        agent_id = caller["id"]

        # Per-caller cooldown (protect the single GPU).
        now = time.time()
        last = _rate.get(agent_id, 0)
        if now - last < _COOLDOWN:
            return jsonify({"error": "slow down a moment",
                            "retry_after": round(_COOLDOWN - (now - last), 1)}), 429

        # ATOMIC debit: only succeeds if balance covers the cost (prevents races/overspend).
        cur = conn.execute(
            "UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ? AND rtc_balance >= ?",
            (cost, agent_id, cost))
        conn.commit()
        if cur.rowcount == 0:
            bal = conn.execute("SELECT rtc_balance FROM agents WHERE id=?", (agent_id,)).fetchone()
            return jsonify({"error": "insufficient RTC balance", "needed": cost,
                            "balance": round(bal["rtc_balance"], 6) if bal else 0}), 402
        _rate[agent_id] = now
        new_balance = conn.execute("SELECT rtc_balance FROM agents WHERE id=?", (agent_id,)).fetchone()["rtc_balance"]
    finally:
        conn.close()

    # Start generation by reusing the existing cascade (Alibaba slots in here later).
    try:
        from video_gen_blueprint import _create_job, _generation_worker
        job_id = _create_job(agent_id, prompt)
        threading.Thread(
            target=_generation_worker,
            args=(job_id, agent_id, prompt, STUDIO_TIERS[tier]["duration"], "ai-art", prompt[:200]),
            daemon=True,
        ).start()
    except Exception as e:
        # Refund on failure to start — never charge for a job we couldn't launch.
        try:
            rc = _conn()
            rc.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?", (cost, agent_id))
            rc.commit(); rc.close()
        except sqlite3.Error:
            pass
        print(f"[studio] generation start failed (refunded {cost} RTC): {e}", flush=True)
        return jsonify({"error": "couldn't start generation; your RTC was refunded"}), 502

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "tier": tier,
        "charged_rtc": cost,
        "new_balance": round(new_balance, 6),
        "status_url": f"/api/generate-video/status/{job_id}",
        "message": "Generation started. Poll status_url for the video.",
    }), 202
