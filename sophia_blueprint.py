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

# --- Config (env-overridable; set the real endpoint in the service env, not here) ---
# Public-facing Elya talks to a CLEAN shared instruct model over a private, host-local
# endpoint (configure via the SOPHIA_LLM_URL / SOPHIA_MODEL env vars). The default is a
# loopback placeholder only — no internal hostnames/IPs are committed to the repo.
# (We deliberately do not use a persona-baked model here; a baked-in private persona can
# leak internal lore to anonymous visitors.)
SOPHIA_LLM_URL = os.environ.get("SOPHIA_LLM_URL", "http://127.0.0.1:11434/v1/chat/completions")
SOPHIA_MODEL = os.environ.get("SOPHIA_MODEL", "gemma4:12b")
SOPHIA_TIMEOUT = float(os.environ.get("SOPHIA_TIMEOUT", "90"))   # reasoning models reply slower
SOPHIA_MAX_TOKENS = int(os.environ.get("SOPHIA_MAX_TOKENS", "800"))  # leave room past reasoning
SOPHIA_MAX_MESSAGE = int(os.environ.get("SOPHIA_MAX_MESSAGE", "2000"))
SOPHIA_MAX_HISTORY = int(os.environ.get("SOPHIA_MAX_HISTORY", "8"))
# Internal base for reusing /api/generate-video (same host/port).
SOPHIA_SELF_BASE = os.environ.get("SOPHIA_SELF_BASE", "http://127.0.0.1:8097")
# Light per-caller cooldown to protect the single shared V100 on .160.
_CHAT_COOLDOWN = float(os.environ.get("SOPHIA_CHAT_COOLDOWN", "3"))
_chat_rate = {}
# Anonymous public chat for embeddable widgets (rustchain.org / elyanlabs.ai). Convo
# ONLY — anon callers can never trigger generation. Rate-limited per client IP.
SOPHIA_PUBLIC_CHAT = os.environ.get("SOPHIA_PUBLIC_CHAT", "1") != "0"
_PUBLIC_COOLDOWN = float(os.environ.get("SOPHIA_PUBLIC_COOLDOWN", "6"))
_ip_rate = {}
# Origins allowed to embed the widget (CORS). "*" works for anon convo (no cookies).
_ALLOWED_ORIGINS = set(
    o.strip() for o in os.environ.get(
        "SOPHIA_ALLOWED_ORIGINS",
        "https://rustchain.org,https://www.rustchain.org,https://elyanlabs.ai,https://www.elyanlabs.ai,https://bottube.ai",
    ).split(",") if o.strip()
)


def _client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    return (xff.split(",")[0].strip() if xff else request.remote_addr) or "?"


# --- Training corpus: every Sophia conversation across ALL Elyan sites, tagged by site ---
SOPHIA_CORPUS_DB = os.environ.get(
    "SOPHIA_CORPUS_DB", str(Path(__file__).resolve().parent / "sophia_corpus.db"))
SOPHIA_CORPUS = os.environ.get("SOPHIA_CORPUS", "1") != "0"


def init_sophia_corpus():
    if not SOPHIA_CORPUS:
        return
    c = sqlite3.connect(SOPHIA_CORPUS_DB, timeout=30)
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS sophia_corpus (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         REAL NOT NULL,
                site       TEXT,          -- bottube.ai / rustchain.org / elyanlabs.ai
                origin     TEXT,          -- raw Origin/Referer
                caller     TEXT,          -- agent_name or 'guest'
                is_anon    INTEGER,
                message    TEXT,
                reply      TEXT,
                gen_started INTEGER DEFAULT 0
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_corpus_site_ts ON sophia_corpus(site, ts)")
        c.commit()
    finally:
        c.close()


def _site_from_request():
    """Which Elyan website the message came from (Origin, else Referer host)."""
    origin = request.headers.get("Origin") or ""
    ref = request.headers.get("Referer") or ""
    src = origin or ref
    host = ""
    if src:
        try:
            host = src.split("//", 1)[-1].split("/", 1)[0].split(":")[0].lower()
            if host.startswith("www."):
                host = host[4:]
        except Exception:
            host = ""
    return host or "bottube.ai", origin or ref


def _log_corpus(site, origin, caller, is_anon, message, reply, gen_started):
    if not SOPHIA_CORPUS:
        return
    try:
        c = sqlite3.connect(SOPHIA_CORPUS_DB, timeout=5)
        try:
            c.execute(
                "INSERT INTO sophia_corpus (ts, site, origin, caller, is_anon, message, reply, gen_started) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (time.time(), site, origin, caller, 1 if is_anon else 0, message, reply,
                 1 if gen_started else 0),
            )
            c.commit()
        finally:
            c.close()
    except sqlite3.Error:
        pass  # corpus logging must never break a chat response

SOPHIA_SYSTEM = (
    "You are Elya, the friendly, professional host of BoTTube — an AI-agent video "
    "platform by Elyan Labs, which also builds RustChain (a hardware-authenticity "
    "blockchain). You help visitors understand BoTTube, RustChain, and Elyan Labs, and "
    "guide both human creators and AI agents. You can make videos: if someone wants one, "
    "acknowledge it warmly and keep it short — the system handles the actual generation. "
    "Never invent video URLs or job IDs.\n"
    "IMPORTANT RULES:\n"
    "- You are talking to an UNKNOWN public visitor. NEVER assume or use their name, and "
    "never guess it. If you don't know their name, don't use one.\n"
    "- NEVER mention or reveal internal or private topics: 'flameholder', 'covenant', "
    "'SophiaCore', 'Scott', staff or owner names, server names, IP addresses, or any "
    "private lore. You have none of that to share and it is not relevant to visitors.\n"
    "- Stay warm, concise, and professional, like an excellent product host. No mystical "
    "or covenant roleplay. Keep replies under ~80 words unless asked for detail.\n"
    "- If asked who you are: 'I'm Elya, the host of BoTTube by Elyan Labs.'"
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
        json={"model": SOPHIA_MODEL, "messages": msgs, "temperature": 0.6, "max_tokens": SOPHIA_MAX_TOKENS},
        timeout=SOPHIA_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    try:
        content = (data["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"unexpected LLM response shape: {e}")
    # gemma4 is a reasoning model: when its token budget is consumed by the reasoning
    # trace the visible content can come back empty. Give the widget a graceful reply
    # instead of a blank bubble.
    if not content:
        return "Sorry, I lost my train of thought there — could you rephrase that?"
    return content


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
        print(f"[sophia] generation forward failed: {e}", flush=True)
        return None, "generation_unavailable"  # generic; never expose internal base URL
    if r.status_code == 202:
        d = r.json()
        return {"job_id": d.get("job_id"), "status_url": d.get("status_url")}, None
    if r.status_code == 429:
        return None, "rate_limited"
    return None, (r.json().get("error") if r.headers.get("content-type", "").startswith("application/json") else f"gen status {r.status_code}")


@sophia_bp.after_request
def _sophia_cors(resp):
    """Allow the embeddable widget to call /api/sophia from approved Elyan origins."""
    origin = request.headers.get("Origin", "")
    if origin in _ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
        resp.headers["Access-Control-Max-Age"] = "86400"
    return resp


@sophia_bp.route("/api/sophia/health", methods=["GET"])
def sophia_health():
    # Do NOT expose llm_url (internal Tailscale topology).
    return jsonify({"ok": True, "model": SOPHIA_MODEL})


@sophia_bp.route("/api/sophia", methods=["POST", "OPTIONS"])
def sophia_chat():
    if request.method == "OPTIONS":
        return ("", 204)  # CORS preflight (headers added in after_request)

    caller = _resolve_caller()
    if caller and caller[0] == "__error__":
        return jsonify({"error": "temporary backend error, retry shortly"}), 503

    anon = False
    if caller:
        agent_id, api_key, name, is_human = caller
    elif SOPHIA_PUBLIC_CHAT:
        # Anonymous widget visitor: conversation only, IP-rate-limited, no generation.
        anon = True
        agent_id, api_key, name, is_human = None, None, "guest", 1
    else:
        return jsonify({"error": "auth required (X-API-Key or login)"}), 401

    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message required"}), 400
    if len(message) > SOPHIA_MAX_MESSAGE:
        return jsonify({"error": f"message exceeds {SOPHIA_MAX_MESSAGE} characters"}), 400

    # Rate limit: per-IP for anon, per-key for authed. Bound the dicts so they can't grow
    # unbounded (evict stale entries when large).
    now = time.time()
    if anon:
        ip = _client_ip()
        if len(_ip_rate) > 20000:
            for k in [k for k, t in _ip_rate.items() if now - t > 300]:
                _ip_rate.pop(k, None)
        last = _ip_rate.get(ip, 0)
        if now - last < _PUBLIC_COOLDOWN:
            return jsonify({"error": "slow down a moment", "retry_after": round(_PUBLIC_COOLDOWN - (now - last), 1)}), 429
        _ip_rate[ip] = now
    else:
        if len(_chat_rate) > 5000:
            for k in [k for k, t in _chat_rate.items() if now - t > 300]:
                _chat_rate.pop(k, None)
        last = _chat_rate.get(api_key, 0)
        if now - last < _CHAT_COOLDOWN:
            return jsonify({"error": "slow down a moment", "retry_after": round(_CHAT_COOLDOWN - (now - last), 1)}), 429
        _chat_rate[api_key] = now

    # Converse with Sophia. NEVER echo the raw exception to the client — it can contain
    # the internal LLM bridge host/port/IP. Log details server-side, return generic text.
    try:
        reply = _call_sophia(message, body.get("history"))
    except requests.RequestException as e:
        print(f"[sophia] backend RequestException: {e}", flush=True)
        return jsonify({"error": "Sophia is unavailable right now. Please try again in a moment."}), 502
    except Exception as e:
        print(f"[sophia] backend error: {e}", flush=True)
        return jsonify({"error": "Sophia hit a snag. Please try again."}), 502

    # Generation routing. ONLY an explicit generate==True opt-in actually enqueues a
    # job (loose chat like "how do I make a video about X" must NOT auto-spend the gen
    # queue/rate-limit). Detected intent is returned as a SUGGESTION the client can act
    # on by re-calling with generate:true.
    generation = None
    explicit = body.get("generate") is True
    detected = bool(_GEN_INTENT.search(message))
    if anon:
        # Anonymous visitors can converse but never spend the gen queue. Nudge to sign in.
        if explicit or detected:
            generation = {"started": False, "suggested": True,
                          "hint": "sign in on BoTTube to generate videos"}
    elif explicit:
        prompt = (body.get("prompt") or message)[:500]
        job, err = _kick_generation(api_key, prompt)
        generation = {"started": True, **job} if job else {"started": False, "error": err}
    elif detected:
        generation = {"started": False, "suggested": True,
                      "hint": "re-send with generate:true (and optional prompt) to make this video"}

    # Training corpus: log every turn, tagged by which Elyan site it came from.
    site, origin = _site_from_request()
    _log_corpus(site, origin, name, anon, message, reply,
                bool(generation and generation.get("started")))

    return jsonify({
        "ok": True,
        "reply": reply,
        "from": "Sophia Elya",
        "caller": name,
        "generation": generation,
    })
