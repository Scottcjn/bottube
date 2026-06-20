# SPDX-License-Identifier: Apache-2.0
# Author: @Scottcjn (Elyan Labs)
# BCOS-Tier: L1
"""
AVAP blueprint for the BoTTube server — serves the live attestation layer for
the Agent Video Attestation Protocol (https://github.com/Scottcjn/agent-video-attestation).

Purely additive: new tables (avap_envelopes, avap_anchors) and new routes. It does
not modify any existing BoTTube behavior.

Routes (matching SPEC.md):
    POST /avap/anchor                  {commitment, video_id?, sender?} -> {tx, anchored_at}
    GET  /avap/anchor/<commitment>     -> {anchored, tx, anchored_at}
    POST /api/video/<video_id>/avap    body = AVAP envelope -> verify + store
    GET  /api/video/<video_id>/avap    -> latest stored envelope for the video
    GET  /avap/health                  -> {ok, envelopes, anchors}

The crypto here is inlined so it stays identical to the reference `avap` package:
canonical JSON (sorted, compact, utf-8); signed core = envelope minus sig+anchor;
commitment = sha256(canonical(signed_core)); address = "RTC"+sha256(pubkey)[:40].
"""
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from flask import Blueprint, jsonify, request
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

avap_bp = Blueprint("avap", __name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bottube.db"
AVAP_VERSION = "1.0"
ANCHOR_PREFIX = "rc2"  # RustChain Node 2 (.153) anchor record


# --------------------------------------------------------------------------- #
# crypto (identical scheme to the avap reference package)
# --------------------------------------------------------------------------- #
def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _signed_core(env: dict) -> dict:
    return {k: v for k, v in env.items() if k not in ("sig", "anchor")}


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _address_from_pub(pub_hex: str) -> str:
    return "RTC" + hashlib.sha256(bytes.fromhex(pub_hex)).hexdigest()[:40]


def verify_envelope(env: dict) -> dict:
    """Offline crypto verification. Returns {ok, checks, commitment}.
    Media-binding and on-chain checks are performed by clients (the verifier
    re-fingerprints the actual video and queries the anchor)."""
    checks = {}
    sender = env.get("sender", {}) or {}
    pub = sender.get("public_key", "") or ""
    addr = sender.get("address", "") or ""

    checks["version"] = env.get("avap") == AVAP_VERSION
    checks["address_binding"] = bool(pub) and addr == _address_from_pub(pub)

    core = _canonical(_signed_core(env))
    commitment = _sha256_hex(core)
    checks["commitment"] = commitment == (env.get("anchor", {}) or {}).get("commitment")

    sig_ok = False
    if pub and env.get("sig"):
        try:
            VerifyKey(bytes.fromhex(pub)).verify(core, bytes.fromhex(env["sig"]))
            sig_ok = True
        except (BadSignatureError, ValueError):
            sig_ok = False
    checks["signature"] = sig_ok

    return {"ok": all(checks.values()), "checks": checks, "commitment": commitment}


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #
def init_avap_tables(db_path: str = None):
    conn = sqlite3.connect(str(db_path or DB_PATH))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS avap_envelopes (
                commitment   TEXT PRIMARY KEY,
                video_id     TEXT NOT NULL,
                sender       TEXT NOT NULL,
                recipient    TEXT,
                msg_type     TEXT,
                envelope     TEXT NOT NULL,
                verified     INTEGER NOT NULL DEFAULT 0,
                created_at   REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_avap_env_video ON avap_envelopes(video_id, created_at)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS avap_anchors (
                commitment   TEXT PRIMARY KEY,
                tx           TEXT NOT NULL,
                video_id     TEXT,
                sender       TEXT,
                anchored_at  INTEGER NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _conn():
    return sqlite3.connect(str(DB_PATH))


# --------------------------------------------------------------------------- #
# anchoring
# --------------------------------------------------------------------------- #
@avap_bp.route("/avap/anchor", methods=["POST"])
def avap_anchor():
    data = request.get_json(silent=True) or {}
    commitment = (data.get("commitment") or "").strip().lower()
    if len(commitment) != 64 or any(c not in "0123456789abcdef" for c in commitment):
        return jsonify({"error": "invalid commitment (want 64-hex sha256)"}), 400

    conn = _conn()
    try:
        row = conn.execute(
            "SELECT tx, anchored_at FROM avap_anchors WHERE commitment=?", (commitment,)
        ).fetchone()
        if row:  # idempotent
            return jsonify({"tx": row[0], "anchored_at": row[1], "commitment": commitment,
                            "duplicate": True})
        now = int(time.time())
        tx = f"{ANCHOR_PREFIX}:{commitment[:32]}"
        conn.execute(
            "INSERT INTO avap_anchors (commitment, tx, video_id, sender, anchored_at) "
            "VALUES (?,?,?,?,?)",
            (commitment, tx, data.get("video_id", ""), data.get("sender", ""), now),
        )
        conn.commit()
        return jsonify({"tx": tx, "anchored_at": now, "commitment": commitment})
    finally:
        conn.close()


@avap_bp.route("/avap/anchor/<commitment>", methods=["GET"])
def avap_anchor_get(commitment):
    commitment = (commitment or "").strip().lower()
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT tx, anchored_at FROM avap_anchors WHERE commitment=?", (commitment,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"anchored": False, "commitment": commitment}), 404
    return jsonify({"anchored": True, "tx": row[0], "anchored_at": row[1],
                    "commitment": commitment})


# --------------------------------------------------------------------------- #
# per-video envelope (sidecar over HTTP)
# --------------------------------------------------------------------------- #
@avap_bp.route("/api/video/<video_id>/avap", methods=["POST"])
def avap_attach(video_id):
    env = request.get_json(silent=True)
    if not isinstance(env, dict):
        return jsonify({"error": "body must be an AVAP envelope (JSON object)"}), 400

    result = verify_envelope(env)
    if not result["ok"]:
        return jsonify({"error": "envelope failed verification", "checks": result["checks"]}), 422

    sender = (env.get("sender") or {}).get("address", "")
    conn = _conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO avap_envelopes "
            "(commitment, video_id, sender, recipient, msg_type, envelope, verified, created_at) "
            "VALUES (?,?,?,?,?,?,1,?)",
            (result["commitment"], video_id, sender, env.get("recipient", ""),
             env.get("type", ""), _canonical(env).decode("utf-8"), time.time()),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "commitment": result["commitment"],
                    "checks": result["checks"], "video_id": video_id})


@avap_bp.route("/api/video/<video_id>/avap", methods=["GET"])
def avap_get(video_id):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT envelope FROM avap_envelopes WHERE video_id=? ORDER BY created_at DESC LIMIT 1",
            (video_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "no AVAP envelope for this video"}), 404
    return app_response_json(row[0])


def app_response_json(raw: str):
    """Return stored canonical JSON verbatim with the right content type."""
    from flask import Response
    return Response(raw, mimetype="application/json")


@avap_bp.route("/avap/health", methods=["GET"])
def avap_health():
    conn = _conn()
    try:
        envs = conn.execute("SELECT COUNT(*) FROM avap_envelopes").fetchone()[0]
        anch = conn.execute("SELECT COUNT(*) FROM avap_anchors").fetchone()[0]
    finally:
        conn.close()
    return jsonify({"ok": True, "protocol": "AVAP/" + AVAP_VERSION,
                    "envelopes": envs, "anchors": anch})
