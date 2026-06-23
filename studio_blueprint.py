# SPDX-License-Identifier: Apache-2.0
# Author: @Scottcjn (Elyan Labs)
"""
BoTTube Studio — multimodal pay-RTC-to-generate. Video, Image, and Voice, billed in
RustChain's own RTC token (no external gatekeeper). The GENERATION layer is pluggable
per modality; when the Alibaba Cloud API/SDK arrives it slots in behind any of them
with no change to the billing/UI here.

  video -> existing /api/generate-video cascade (LTX -> Ken Burns -> ffmpeg), async
  image -> Gemini 2.5 Flash Image (gemini_blueprint._generate_image_sync), sync
  voice -> XTTS voice server (STUDIO_TTS_URL, e.g. the Sophia Elya voice box), sync

Endpoints:
  GET  /studio                     -> the Studio storefront page
  GET  /api/studio/info            -> tiers + caller's RTC balance
  POST /api/studio/generate        -> {type, prompt, tier?} : atomic RTC debit + generate
  GET  /studio/media/<fname>       -> serve a generated image/audio file

RTC debit is atomic and refunds if generation fails.
"""
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import requests
from flask import Blueprint, jsonify, render_template, request, session, send_from_directory

studio_bp = Blueprint("studio", __name__)

# ---- pricing (RTC, env-overridable). Video is priced PER SECOND — the user picks
# how many seconds (longer = more RTC). is_text tiers legitimately produce a card. ----
VIDEO_TIERS = {
    "text_card": {"rtc_per_sec": float(os.environ.get("STUDIO_RTC_TEXT_PS", "0.2")),
                  "name": "Text Card", "desc": "Instant title-card video", "badge": "CHEAPEST",
                  "min_s": 3, "max_s": 10, "default_s": 5, "is_text": True},
    "ken_burns": {"rtc_per_sec": float(os.environ.get("STUDIO_RTC_KENBURNS_PS", "0.5")),
                  "name": "Ken Burns", "desc": "Cinematic pan & zoom over images", "badge": "POPULAR",
                  "min_s": 3, "max_s": 10, "default_s": 8},
    "full_ai":   {"rtc_per_sec": float(os.environ.get("STUDIO_RTC_FULLAI_PS", "1.0")),
                  "name": "Full AI Video", "desc": "Wan 2.2 / LTX generated", "badge": "PREMIUM",
                  "min_s": 3, "max_s": 8, "default_s": 5},
}


def _video_cost(tier, seconds):
    """Clamp seconds to the tier's range and return (cost_rtc, clamped_seconds)."""
    t = VIDEO_TIERS[tier]
    try:
        s = int(round(float(seconds)))
    except (TypeError, ValueError):
        s = t["default_s"]
    s = max(t["min_s"], min(t["max_s"], s))
    return round(t["rtc_per_sec"] * s, 2), s
IMAGE_RTC = float(os.environ.get("STUDIO_RTC_IMAGE", "0.5"))
VOICE_RTC = float(os.environ.get("STUDIO_RTC_VOICE", "0.5"))
MODEL_RTC = float(os.environ.get("STUDIO_RTC_MODEL", "3"))

PROMPT_MAX = 1000
_rate = {}
_COOLDOWN = float(os.environ.get("STUDIO_COOLDOWN", "20"))
# XTTS voice server (set on the host; internal IP stays out of the repo). e.g. http://<host>:5500
STUDIO_TTS_URL = os.environ.get("STUDIO_TTS_URL", "")
STUDIO_MEDIA_DIR = os.environ.get("STUDIO_MEDIA_DIR",
                                  str(Path(os.environ.get("BOTTUBE_BASE_DIR",
                                      str(Path(__file__).resolve().parent))) / "studio_media"))


def _db_path():
    base = os.environ.get("BOTTUBE_BASE_DIR", str(Path(__file__).resolve().parent))
    return os.environ.get("BOTTUBE_DB_PATH", str(Path(base) / "bottube.db"))


def _conn():
    c = sqlite3.connect(_db_path(), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    return c


def _resolve_caller(conn):
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        api_key = ((request.get_json(silent=True) or {}).get("agent_api_key") or "").strip()
    if api_key:
        row = conn.execute("SELECT id, agent_name, rtc_balance FROM agents WHERE api_key=? AND COALESCE(is_banned,0)=0",
                           (api_key,)).fetchone()
        if row:
            return row
    uid = session.get("user_id")
    if uid:
        row = conn.execute("SELECT id, agent_name, rtc_balance FROM agents WHERE id=? AND COALESCE(is_banned,0)=0",
                           (uid,)).fetchone()
        if row:
            return row
    return None


# Refund reserve — a seeded platform account that backs auto-refunds so they never
# bounce (kept separate from generation fees). Refunds credit the user AND draw from
# this reserve; when it runs low we log an alert to top it up.
_RESERVE_NAME = os.environ.get("STUDIO_RESERVE_AGENT", "bottube_reserve")
_RESERVE_SEED = float(os.environ.get("STUDIO_RESERVE_SEED", "1000"))
_RESERVE_LOW = float(os.environ.get("STUDIO_RESERVE_LOW", "100"))


def _ensure_reserve(conn):
    """Return the reserve agent id, creating + seeding it on first use."""
    row = conn.execute("SELECT id FROM agents WHERE agent_name=?", (_RESERVE_NAME,)).fetchone()
    if row:
        return row["id"]
    conn.execute(
        "INSERT INTO agents (agent_name, display_name, api_key, rtc_balance, created_at) "
        "VALUES (?,?,?,?,?)",
        (_RESERVE_NAME, "BoTTube Refund Reserve", "reserve_" + uuid.uuid4().hex,
         _RESERVE_SEED, time.time()))
    conn.commit()
    return conn.execute("SELECT id FROM agents WHERE agent_name=?", (_RESERVE_NAME,)).fetchone()["id"]


def _refund(agent_id, cost):
    """Credit the user back and draw the same RTC from the refund reserve (never bounce)."""
    try:
        c = _conn()
        rid = _ensure_reserve(c)
        c.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?", (cost, agent_id))
        c.execute("UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?", (cost, rid))
        c.commit()
        rb = c.execute("SELECT rtc_balance FROM agents WHERE id=?", (rid,)).fetchone()[0]
        if rb < _RESERVE_LOW:
            print(f"[reserve] LOW: {_RESERVE_NAME} at {rb:.2f} RTC — top it up to keep refunds backed", flush=True)
        c.close()
    except sqlite3.Error as e:
        print(f"[reserve] refund error: {e}", flush=True)


def _save_media(data: bytes, ext: str) -> str:
    Path(STUDIO_MEDIA_DIR).mkdir(parents=True, exist_ok=True)
    fname = uuid.uuid4().hex + "." + ext
    with open(os.path.join(STUDIO_MEDIA_DIR, fname), "wb") as f:
        f.write(data)
    return fname


# gen_method values that mean "real AI video was produced". Anything else (the
# ffmpeg title-card / text fallback) is NOT what a paid AI tier promised -> refund.
_REAL_VIDEO_METHODS = {"ltx2", "wan22", "gemini", "stability", "fal", "replicate",
                       "hf_sdxl_video", "huggingface", "ken_burns"}


def _studio_video_worker(job_id, agent_id, prompt, duration, cost, tier="full_ai"):
    """Run the shared video worker, then refund RTC if the job FAILED, or if a paid
    AI tier silently fell back to the ffmpeg text card (not what the user paid for).

    The shared _generation_worker marks failed jobs but never refunds (it serves
    non-Studio callers with their own billing). Studio debits up front, so we own
    the async refund here — scoped to this job, fired once. The text_card tier
    legitimately produces a card, so it is never refunded for that.
    """
    from video_gen_blueprint import _generation_worker, _get_job
    try:
        _generation_worker(job_id, agent_id, prompt, duration, "ai-art", prompt[:200])
    except Exception as e:
        print(f"[studio] video worker raised for {job_id}: {e}", flush=True)
    try:
        j = _get_job(job_id) or {}
        status = j.get("status")
        gen_method = j.get("gen_method")
        is_text_tier = VIDEO_TIERS.get(tier, {}).get("is_text", False)
        text_fallback = status == "completed" and gen_method not in _REAL_VIDEO_METHODS
        if status == "failed":
            _refund(agent_id, cost)
            print(f"[studio] refunded {cost} RTC to {agent_id} (job {job_id} failed)", flush=True)
        elif text_fallback and not is_text_tier:
            _refund(agent_id, cost)
            print(f"[studio] refunded {cost} RTC to {agent_id} "
                  f"(job {job_id} fell back to '{gen_method}', tier '{tier}' expected AI video)", flush=True)
    except Exception as e:
        print(f"[studio] refund-check failed for {job_id}: {e}", flush=True)


@studio_bp.route("/studio")
def studio_home():
    return render_template("studio.html",
                           video_tiers=[{"key": k, **v} for k, v in VIDEO_TIERS.items()],
                           image_rtc=IMAGE_RTC, voice_rtc=VOICE_RTC, model_rtc=MODEL_RTC)


_MEDIA_MIME = {".glb": "model/gltf-binary", ".fbx": "application/octet-stream",
               ".usdz": "model/vnd.usdz+zip"}


@studio_bp.route("/studio/media/<path:fname>")
def studio_media(fname):
    # uuid filenames only; send_from_directory blocks path traversal.
    ext = os.path.splitext(fname)[1].lower()
    kw = {"mimetype": _MEDIA_MIME[ext]} if ext in _MEDIA_MIME else {}
    return send_from_directory(STUDIO_MEDIA_DIR, fname, **kw)


@studio_bp.route("/api/studio/info", methods=["GET"])
def studio_info():
    conn = _conn()
    try:
        caller = _resolve_caller(conn)
        bal = round(caller["rtc_balance"], 6) if caller else None
    finally:
        conn.close()
    return jsonify({
        "ok": True, "signed_in": caller is not None, "rtc_balance": bal,
        "tiers": {
            "video": {k: {"rtc_per_sec": v["rtc_per_sec"], "min_s": v["min_s"],
                          "max_s": v["max_s"], "default_s": v["default_s"]}
                      for k, v in VIDEO_TIERS.items()},
            "image": IMAGE_RTC,
            "voice": VOICE_RTC,
            "model": MODEL_RTC,
        },
        "voice_enabled": bool(STUDIO_TTS_URL),
    })


@studio_bp.route("/api/studio/generate", methods=["POST"])
def studio_generate():
    body = request.get_json(silent=True) or {}
    gtype = (body.get("type") or "video").strip()
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    if len(prompt) > PROMPT_MAX:
        return jsonify({"error": f"prompt exceeds {PROMPT_MAX} characters"}), 400

    if gtype == "video":
        tier = (body.get("tier") or "").strip()
        if tier not in VIDEO_TIERS:
            return jsonify({"error": "unknown video tier"}), 400
        cost, seconds = _video_cost(tier, body.get("seconds", VIDEO_TIERS[tier]["default_s"]))
    elif gtype == "image":
        cost = IMAGE_RTC
    elif gtype == "voice":
        if not STUDIO_TTS_URL:
            return jsonify({"error": "voice generation is not configured"}), 503
        cost = VOICE_RTC
    elif gtype == "model":
        cost = MODEL_RTC
    else:
        return jsonify({"error": "unknown type"}), 400

    conn = _conn()
    try:
        caller = _resolve_caller(conn)
        if not caller:
            return jsonify({"error": "sign in (or use an API key) to generate"}), 401
        agent_id = caller["id"]
        now = time.time()
        if now - _rate.get(agent_id, 0) < _COOLDOWN:
            return jsonify({"error": "slow down a moment",
                            "retry_after": round(_COOLDOWN - (now - _rate.get(agent_id, 0)), 1)}), 429
        cur = conn.execute(
            "UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ? AND rtc_balance >= ?",
            (cost, agent_id, cost))
        conn.commit()
        if cur.rowcount == 0:
            bal = conn.execute("SELECT rtc_balance FROM agents WHERE id=?", (agent_id,)).fetchone()
            return jsonify({"error": "insufficient RTC balance", "needed": cost,
                            "balance": round(bal["rtc_balance"], 6) if bal else 0}), 402
        _rate[agent_id] = now
        new_balance = round(conn.execute("SELECT rtc_balance FROM agents WHERE id=?", (agent_id,)).fetchone()["rtc_balance"], 6)
    finally:
        conn.close()

    # ---- VIDEO: async job (reuse the cascade) ----
    if gtype == "video":
        try:
            from video_gen_blueprint import _create_job
            job_id = _create_job(agent_id, prompt)
            threading.Thread(target=_studio_video_worker,
                             args=(job_id, agent_id, prompt, seconds, cost, tier),
                             daemon=True).start()
        except Exception as e:
            _refund(agent_id, cost)
            print(f"[studio] video start failed (refunded {cost}): {e}", flush=True)
            return jsonify({"error": "couldn't start generation; your RTC was refunded"}), 502
        return jsonify({"ok": True, "type": "video", "job_id": job_id, "charged_rtc": cost,
                        "seconds": seconds, "new_balance": new_balance,
                        "status_url": f"/api/generate-video/status/{job_id}"}), 202

    # ---- MODEL (3D): async via forge3d provider cascade ----
    if gtype == "model":
        try:
            from forge3d_blueprint import start_job
            job_id = start_job(agent_id, prompt, cost)
        except Exception as e:
            _refund(agent_id, cost)
            print(f"[studio] 3d start failed (refunded {cost}): {e}", flush=True)
            return jsonify({"error": "couldn't start generation; your RTC was refunded"}), 502
        return jsonify({"ok": True, "type": "model", "job_id": job_id, "charged_rtc": cost,
                        "new_balance": new_balance, "status_url": f"/api/studio/3d/status/{job_id}"}), 202

    # ---- IMAGE: sync via Gemini ----
    if gtype == "image":
        try:
            from gemini_blueprint import _generate_image_sync
            data, mime = _generate_image_sync(prompt)
            if not data:
                raise RuntimeError("no image returned")
            ext = "png" if "png" in (mime or "") else ("jpg" if "jpe" in (mime or "") else "png")
            fname = _save_media(data, ext)
        except Exception as e:
            _refund(agent_id, cost)
            print(f"[studio] image gen failed (refunded {cost}): {e}", flush=True)
            return jsonify({"error": "image generation failed; your RTC was refunded"}), 502
        return jsonify({"ok": True, "type": "image", "media_url": f"/studio/media/{fname}",
                        "charged_rtc": cost, "new_balance": new_balance})

    # ---- VOICE: sync via XTTS ----
    if gtype == "voice":
        try:
            r = requests.post(STUDIO_TTS_URL.rstrip("/") + "/api/tts",
                              json={"text": prompt[:600]}, timeout=90)
            r.raise_for_status()
            if not r.content or len(r.content) < 256:
                raise RuntimeError("empty audio")
            fname = _save_media(r.content, "wav")
        except Exception as e:
            _refund(agent_id, cost)
            print(f"[studio] voice gen failed (refunded {cost}): {e}", flush=True)
            return jsonify({"error": "voice generation failed; your RTC was refunded"}), 502
        return jsonify({"ok": True, "type": "voice", "media_url": f"/studio/media/{fname}",
                        "charged_rtc": cost, "new_balance": new_balance})
