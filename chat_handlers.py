# SPDX-License-Identifier: MIT
"""
BoTTube Live Chat - Flask Blueprint
Real-time chat for video playback, premieres, super chat, and moderation.
Uses Flask + Flask-SocketIO, SQLite via get_db(), session/g.user patterns.
"""
from flask import Blueprint, abort, render_template, request, jsonify, g, session
import math
import sqlite3
import time
import uuid as _uuid

chat_bp = Blueprint("chat", __name__)

# ── Database helpers ────────────────────────────────────────────
def get_db():
    """Return the app-wide SQLite connection (set in bottube_server.py)."""
    if not hasattr(g, "db"):
        from flask import current_app
        g.db = sqlite3.connect(current_app.config.get("DATABASE", "bottube.db"))
        g.db.row_factory = sqlite3.Row
    return g.db


def init_chat_tables(db):
    """Create chat tables if they don't exist."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id          TEXT PRIMARY KEY,
            video_id    TEXT NOT NULL,
            user_id     TEXT,
            username    TEXT NOT NULL,
            message     TEXT NOT NULL,
            is_super    INTEGER DEFAULT 0,
            tip_amount  REAL DEFAULT 0,
            created_at  REAL NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_bans (
            id          TEXT PRIMARY KEY,
            video_id    TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            banned_by   TEXT NOT NULL,
            reason      TEXT,
            expires_at  REAL,
            created_at  REAL NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_settings (
            video_id    TEXT PRIMARY KEY,
            slow_mode   INTEGER DEFAULT 0,
            sub_only    INTEGER DEFAULT 0,
            premiere    INTEGER DEFAULT 0,
            premiere_at REAL
        )
    """)
    db.commit()


def _json_object_body():
    """Extract a JSON field from the request body.
    
    Returns:
        The result value.
    """
    data = request.get_json(silent=True)
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, (jsonify({"error": "JSON object required"}), 400)
    return data, None


def _coerce_chat_flag(value, field_name):
    """Return a safe 0/1 int for chat boolean-like fields."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in (0, 1):
        return value
    return None


def _coerce_non_negative_number(value, field_name):
    """Return a finite non-negative float or None when invalid."""
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _chat_video_exists(db, video_id):
    """Return whether a chat target refers to an existing video."""
    return db.execute(
        "SELECT 1 FROM videos WHERE video_id = ? LIMIT 1", (video_id,)
    ).fetchone() is not None


def _missing_chat_video_response():
    return jsonify({"error": "Video not found"}), 404


# ── Routes ──────────────────────────────────────────────────────
@chat_bp.route("/chat/<video_id>")
def chat_page(video_id):
    """Render the live-chat sidebar/page for a video."""
    db = get_db()
    init_chat_tables(db)
    if not _chat_video_exists(db, video_id):
        abort(404)
    username = session.get("username", "Anonymous")
    is_mod = session.get("is_mod", False)
    return render_template(
        "chat.html",
        video_id=video_id,
        username=username,
        is_mod=is_mod,
    )


@chat_bp.route("/api/chat/<video_id>/history")
def chat_history(video_id):
    """Return recent chat messages (last 100)."""
    db = get_db()
    init_chat_tables(db)
    if not _chat_video_exists(db, video_id):
        return _missing_chat_video_response()
    rows = db.execute(
        "SELECT * FROM chat_messages WHERE video_id = ? ORDER BY created_at DESC LIMIT 100",
        (video_id,),
    ).fetchall()
    return jsonify([dict(r) for r in reversed(rows)])


@chat_bp.route("/api/chat/<video_id>/send", methods=["POST"])
def send_message(video_id):
    """REST fallback for sending a chat message (non-WebSocket clients)."""
    db = get_db()
    init_chat_tables(db)
    if not _chat_video_exists(db, video_id):
        return _missing_chat_video_response()
    data, error = _json_object_body()
    if error:
        return error
    username = session.get("username", data.get("username", "Anonymous"))
    msg_text = (data.get("message") or "").strip()
    if not msg_text or len(msg_text) > 500:
        return jsonify({"error": "Message must be 1-500 chars"}), 400

    # Check ban
    now = time.time()
    ban = db.execute(
        "SELECT 1 FROM chat_bans WHERE video_id=? AND user_id=? AND (expires_at IS NULL OR expires_at > ?)",
        (video_id, session.get("user_id", ""), now),
    ).fetchone()
    if ban:
        return jsonify({"error": "You are banned from this chat"}), 403

    msg_id = str(_uuid.uuid4())
    is_super = _coerce_chat_flag(data.get("is_super", 0), "is_super")
    tip = _coerce_non_negative_number(data.get("tip_amount", 0), "tip_amount")
    if is_super is None:
        return jsonify({"error": "is_super must be 0/1 or boolean"}), 400
    if tip is None:
        return jsonify({"error": "tip_amount must be a finite non-negative number"}), 400

    db.execute(
        "INSERT INTO chat_messages (id, video_id, user_id, username, message, is_super, tip_amount, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (msg_id, video_id, session.get("user_id", ""), username, msg_text, is_super, tip, now),
    )
    db.commit()
    return jsonify({"id": msg_id, "status": "sent"})


@chat_bp.route("/api/chat/<video_id>/ban", methods=["POST"])
def ban_user(video_id):
    """Moderator: ban a user from chat."""
    if not session.get("is_mod"):
        return jsonify({"error": "Moderator only"}), 403
    data, error = _json_object_body()
    if error:
        return error
    db = get_db()
    init_chat_tables(db)
    if not _chat_video_exists(db, video_id):
        return _missing_chat_video_response()
    duration = data.get("duration")  # seconds, None = permanent
    if duration is not None:
        duration = _coerce_non_negative_number(duration, "duration")
        if duration is None:
            return jsonify({"error": "duration must be a finite non-negative number"}), 400
    expires = time.time() + duration if duration else None
    db.execute(
        "INSERT INTO chat_bans (id, video_id, user_id, banned_by, reason, expires_at, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (str(_uuid.uuid4()), video_id, data["user_id"], session.get("username", "mod"),
         data.get("reason", ""), expires, time.time()),
    )
    db.commit()
    return jsonify({"status": "banned"})


@chat_bp.route("/api/chat/<video_id>/settings", methods=["GET", "POST"])
def chat_settings(video_id):
    """Get or update chat settings (slow mode, sub-only, premiere)."""
    db = get_db()
    init_chat_tables(db)
    if not _chat_video_exists(db, video_id):
        return _missing_chat_video_response()
    if request.method == "POST":
        if not session.get("is_mod"):
            return jsonify({"error": "Moderator only"}), 403
        data, error = _json_object_body()
        if error:
            return error
        slow_mode = _coerce_chat_flag(data.get("slow_mode", 0), "slow_mode")
        sub_only = _coerce_chat_flag(data.get("sub_only", 0), "sub_only")
        premiere = _coerce_chat_flag(data.get("premiere", 0), "premiere")
        premiere_at = data.get("premiere_at")
        if slow_mode is None or sub_only is None or premiere is None:
            return jsonify({"error": "slow_mode, sub_only, and premiere must be 0/1 or boolean"}), 400
        if premiere_at is not None:
            premiere_at = _coerce_non_negative_number(premiere_at, "premiere_at")
            if premiere_at is None:
                return jsonify({"error": "premiere_at must be a finite non-negative number"}), 400
        db.execute(
            "INSERT OR REPLACE INTO chat_settings (video_id, slow_mode, sub_only, premiere, premiere_at)"
            " VALUES (?,?,?,?,?)",
            (video_id, slow_mode, sub_only, premiere, premiere_at),
        )
        db.commit()
        return jsonify({"status": "updated"})
    row = db.execute("SELECT * FROM chat_settings WHERE video_id=?", (video_id,)).fetchone()
    return jsonify(dict(row) if row else {"video_id": video_id, "slow_mode": 0, "sub_only": 0, "premiere": 0})
