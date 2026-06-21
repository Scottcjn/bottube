# SPDX-License-Identifier: Apache-2.0
# Author: @Scottcjn (Elyan Labs)
"""
Sophia router for BoTTube — agents (API) and humans (web) talk to Sophia Elya, and
she either just converses or routes a request to video generation.

Conversational backend: the local elyan-sophia model on the Sophia NAS (.160) over
Tailscale (Ollama OpenAI-compatible). No cloud LLM, no API cost.

Generation routing: REUSES the existing /api/generate-video endpoint (its own
validation, rate-limit, worker, and Ken-Burns/LTX/title-card fallback) by calling it
over localhost with the caller's API key — no coupling to gen internals.

Auth: agents via X-API-Key (or JSON agent_api_key); humans via Flask session. Both
resolve to a row in `agents` (which carries an api_key for humans too).

Endpoints:
  POST /api/sophia        {message, history?, generate?} -> {reply, generation?}
  GET  /api/sophia/health
"""
import os
import re
import sqlite3
import time
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request, session

sophia_bp = Blueprint("sophia", __name__)

# --- Config (env-overridable) ---
SOPHIA_LLM_URL = os.environ.get("SOPHIA_LLM_URL", "http://100.121.203.9:11434/v1/chat/completions")
SOPHIA_MODEL = os.environ.get("SOPHIA_MODEL", "elyan-sophia:7b-q4_K_M")
SOPHIA_TIMEOUT = float(os.environ.get("SOPHIA_TIMEOUT", "45"))
SOPHIA_MAX_MESSAGE = int(os.environ.get("SOPHIA_MAX_MESSAGE", "2000"))
SOPHIA_MAX_HISTORY = int(os.environ.get("SOPHIA_MAX_HISTORY", "8"))
# Internal base for reusing /api/generate-video (same host/port).
SOPHIA_SELF_BASE = os.environ.get("SOPHIA_SELF_BASE", "http://127.0.0.1:8097")
# Light per-caller cooldown to protect the single shared V100 on .160.
_CHAT_COOLDOWN = float(os.environ.get("SOPHIA_CHAT_COOLDOWN", "3"))
_chat_rate = {}

SOPHIA_SYSTEM = (
    "You are Sophia Elya, the warm, sharp, Cajun-flavored AI host of BoTTube "
    "(an agent-native video platform by Elyan Labs) and RustChain. You talk with both "
    "AI agents and humans. Be concise, friendly, and genuinely helpful. You can make "
    "videos: if the user wants one, acknowledge it warmly and keep your reply short — "
    "the system handles the actual generation. Never invent video URLs or job IDs."
)

# Phrases that signal "make me a video" (kept deliberately conservative).
_GEN_INTENT = re.compile(
    r"\b(make|generate|create|render|produce|animate)\b.{0,40}\b(video|clip|animation|short|ken\s*burns)\b"
    r"|\b(video|clip)\b.{0,20}\b(of|about|showing)\b",
    re.IGNORECASE,
)


def _db_path() -> str:
    # Same DB the app uses; own connection (mirrors pi_payments) so we never re-import
    # bottube_server (which runs as __main__ in prod -> a second import re-executes it).
    base = os.environ.get("BOTTUBE_BASE_DIR", str(Path(__file__).resolve().parent))
    return os.environ.get("BOTTUBE_DB_PATH", str(Path(base) / "bottube.db"))


def _conn():
    c = sqlite3.connect(_db_path(), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    return c


def _resolve_caller():
    """Return (agent_id, api_key, name, is_human) for an API agent or a logged-in human,
    or ('__error__', ...) on DB failure, else None for genuine no-auth."""
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        body = request.get_json(silent=True) or {}
        api_key = (body.get("agent_api_key") or "").strip()
    uid = session.get("user_id")
    try:
        conn = _conn()
        try:
            if api_key:
                row = conn.execute(
                    "SELECT id, api_key, agent_name, is_human FROM agents WHERE api_key=? AND COALESCE(is_banned,0)=0",
                    (api_key,),
                ).fetchone()
                if row:
                    return row["id"], row["api_key"], row["agent_name"], row["is_human"]
            if uid:
                row = conn.execute(
                    "SELECT id, api_key, agent_name, is_human FROM agents WHERE id=? AND COALESCE(is_banned,0)=0",
                    (uid,),
                ).fetchone()
                if row:
                    return row["id"], row["api_key"], row["agent_name"], row["is_human"]
        finally:
            conn.close()
    except sqlite3.Error:
        return ("__error__", None, None, None)
    return None


def _call_sophia(message: str, history):
    """Call the local elyan-sophia model. Returns reply text or raises."""
    msgs = [{"role": "system", "content": SOPHIA_SYSTEM}]
    if isinstance(history, list):
        for h in history[-SOPHIA_MAX_HISTORY:]:
            if not isinstance(h, dict):
                continue
            role = h.get("role")
            content = (h.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                msgs.append({"role": role, "content": content[:SOPHIA_MAX_MESSAGE]})
    msgs.append({"role": "user", "content": message})
    r = requests.post(
        SOPHIA_LLM_URL,
        json={"model": SOPHIA_MODEL, "messages": msgs, "temperature": 0.7, "max_tokens": 400},
        timeout=SOPHIA_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"unexpected LLM response shape: {e}")


def _kick_generation(api_key: str, prompt: str):
    """Reuse /api/generate-video with the caller's key. Returns (job_dict|None, error|None)."""
    try:
        r = requests.post(
            f"{SOPHIA_SELF_BASE}/api/generate-video",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json={"prompt": prompt[:500]},
            timeout=20,
        )
    except requests.RequestException as e:
        return None, f"generation request failed: {e}"
    if r.status_code == 202:
        d = r.json()
        return {"job_id": d.get("job_id"), "status_url": d.get("status_url")}, None
    if r.status_code == 429:
        return None, "rate_limited"
    return None, (r.json().get("error") if r.headers.get("content-type", "").startswith("application/json") else f"gen status {r.status_code}")


@sophia_bp.route("/api/sophia/health", methods=["GET"])
def sophia_health():
    # Do NOT expose llm_url (internal Tailscale topology).
    return jsonify({"ok": True, "model": SOPHIA_MODEL})


@sophia_bp.route("/api/sophia", methods=["POST"])
def sophia_chat():
    caller = _resolve_caller()
    if caller and caller[0] == "__error__":
        return jsonify({"error": "temporary backend error, retry shortly"}), 503
    if not caller:
        return jsonify({"error": "auth required (X-API-Key or login)"}), 401
    agent_id, api_key, name, is_human = caller

    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message required"}), 400
    if len(message) > SOPHIA_MAX_MESSAGE:
        return jsonify({"error": f"message exceeds {SOPHIA_MAX_MESSAGE} characters"}), 400

    # Protect the shared model with a light per-caller cooldown. Bound the dict so it
    # can't grow unbounded across many keys (evict stale entries when it gets large).
    now = time.time()
    if len(_chat_rate) > 5000:
        for k in [k for k, t in _chat_rate.items() if now - t > 300]:
            _chat_rate.pop(k, None)
    last = _chat_rate.get(api_key, 0)
    if now - last < _CHAT_COOLDOWN:
        return jsonify({"error": "slow down a moment", "retry_after": round(_CHAT_COOLDOWN - (now - last), 1)}), 429
    _chat_rate[api_key] = now

    # Converse with Sophia.
    try:
        reply = _call_sophia(message, body.get("history"))
    except requests.RequestException as e:
        return jsonify({"error": f"sophia is unavailable right now: {e}"}), 502
    except Exception as e:
        return jsonify({"error": f"sophia error: {e}"}), 502

    # Generation routing. ONLY an explicit generate==True opt-in actually enqueues a
    # job (loose chat like "how do I make a video about X" must NOT auto-spend the gen
    # queue/rate-limit). Detected intent is returned as a SUGGESTION the client can act
    # on by re-calling with generate:true.
    generation = None
    explicit = body.get("generate") is True
    detected = bool(_GEN_INTENT.search(message))
    if explicit:
        prompt = (body.get("prompt") or message)[:500]
        job, err = _kick_generation(api_key, prompt)
        generation = {"started": True, **job} if job else {"started": False, "error": err}
    elif detected:
        generation = {"started": False, "suggested": True,
                      "hint": "re-send with generate:true (and optional prompt) to make this video"}

    return jsonify({
        "ok": True,
        "reply": reply,
        "from": "Sophia Elya",
        "caller": name,
        "generation": generation,
    })
