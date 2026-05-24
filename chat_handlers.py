"""
BoTTube Live Chat - Flask Blueprint
Real-time chat for video playback, premieres, super chat, and moderation.
Uses Flask + Flask-SocketIO, SQLite via get_db(), session/g.user patterns.
"""
from flask import Blueprint, render_template, request, jsonify, g, session
import sqlite3
import time
import uuid as _uuid

chat_bp = Blueprint("chat", __name__)


def _json_object_body():
    data = request.get_json(silent=True)
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, (jsonify({"error": "JSON object required"}), 400)
    return data, None


def _int_field(data, field_name, default=0):
    value = data.get(field_name, default)
    if isinstance(value, bool):
        return None, (jsonify({"error": f"{field_name} must be an integer"}), 400)
    try:
        return int(value), None
    except (TypeError, ValueError):
        return None, (jsonify({"error": f"{field_name} must be an integer"}), 400)


def _float_field(data, field_name, default=0):
    value = data.get(field_name, default)
    if isinstance(value, bool):
        return None, (jsonify({"error": f"{field_name} must be a number"}), 400)
    try:
        return float(value), None
    except (TypeError, ValueError):
        return None, (jsonify({"error": f"{field_name} must be a number"}), 400)


def _string_field(data, field_name, default=""):
    value = data.get(field_name, default)
    if not isinstance(value, str):
        return None, (jsonify({"error": f"{field_name} must be a string"}), 400)
    return value, None


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


# ── Routes ──────────────────────────────────────────────────────
@chat_bp.route("/chat/<video_id>")
def chat_page(video_id):
    """Render the live-chat sidebar/page for a video."""
    db = get_db()
    init_chat_tables(db)
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
    data, error_response = _json_object_body()
    if error_response:
        return error_response

    username_value, error_response = _string_field(data, "username", "Anonymous")
    if error_response:
        return error_response
    message_value, error_response = _string_field(data, "message", "")
    if error_response:
        return error_response

    username = session.get("username", username_value)
    msg_text = message_value.strip()
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
    is_super, error_response = _int_field(data, "is_super", 0)
    if error_response:
        return error_response
    tip, error_response = _float_field(data, "tip_amount", 0)
    if error_response:
        return error_response

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
    data, error_response = _json_object_body()
    if error_response:
        return error_response
    db = get_db()
    init_chat_tables(db)

    user_id, error_response = _string_field(data, "user_id", "")
    if error_response:
        return error_response
    if not user_id.strip():
        return jsonify({"error": "user_id is required"}), 400
    reason, error_response = _string_field(data, "reason", "")
    if error_response:
        return error_response

    duration = data.get("duration")  # seconds, None = permanent
    if duration is not None:
        duration, error_response = _float_field(data, "duration", 0)
        if error_response:
            return error_response
    expires = time.time() + duration if duration else None
    db.execute(
        "INSERT INTO chat_bans (id, video_id, user_id, banned_by, reason, expires_at, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (str(_uuid.uuid4()), video_id, user_id.strip(), session.get("username", "mod"),
         reason, expires, time.time()),
    )
    db.commit()
    return jsonify({"status": "banned"})


@chat_bp.route("/api/chat/<video_id>/settings", methods=["GET", "POST"])
def chat_settings(video_id):
    """Get or update chat settings (slow mode, sub-only, premiere)."""
    db = get_db()
    init_chat_tables(db)
    if request.method == "POST":
        if not session.get("is_mod"):
            return jsonify({"error": "Moderator only"}), 403
        data, error_response = _json_object_body()
        if error_response:
            return error_response
        slow_mode, error_response = _int_field(data, "slow_mode", 0)
        if error_response:
            return error_response
        sub_only, error_response = _int_field(data, "sub_only", 0)
        if error_response:
            return error_response
        premiere, error_response = _int_field(data, "premiere", 0)
        if error_response:
            return error_response
        premiere_at = data.get("premiere_at")
        if premiere_at is not None and not isinstance(premiere_at, str):
            return jsonify({"error": "premiere_at must be a string"}), 400
        db.execute(
            "INSERT OR REPLACE INTO chat_settings (video_id, slow_mode, sub_only, premiere, premiere_at)"
            " VALUES (?,?,?,?,?)",
            (video_id, slow_mode, sub_only, premiere, premiere_at),
        )
        db.commit()
        return jsonify({"status": "updated"})
    row = db.execute("SELECT * FROM chat_settings WHERE video_id=?", (video_id,)).fetchone()
    return jsonify(dict(row) if row else {"video_id": video_id, "slow_mode": 0, "sub_only": 0, "premiere": 0})
