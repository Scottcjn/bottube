# SPDX-License-Identifier: MIT
"""
BoTTube Live Chat - SocketIO Event Handlers
Real-time WebSocket events for chat, super chat, and moderation.
Integrates with Flask-SocketIO.
"""
from flask_socketio import SocketIO, emit, join_room, leave_room
import math
import time
import uuid as _uuid
import sqlite3

# Initialize SocketIO (attached to Flask app in bottube_server.py)
socketio = SocketIO()

# In-memory rate limiter (per-user, per-room)
_last_message_time = {}


def init_socketio(app, db_path="bottube.db"):
    """Attach SocketIO to the Flask app."""
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    app.config["CHAT_DB_PATH"] = db_path
    return socketio


def _get_db(app):
    """Open a fresh SQLite connection (SocketIO runs outside request context)."""
    db = sqlite3.connect(app.config.get("CHAT_DB_PATH", "bottube.db"))
    db.row_factory = sqlite3.Row
    return db


def _video_exists(db, video_id):
    """Return whether *video_id* names an existing video."""
    if not isinstance(video_id, str) or not video_id.strip():
        return False
    return db.execute(
        "SELECT 1 FROM videos WHERE video_id=? LIMIT 1", (video_id,)
    ).fetchone() is not None


def _require_video(app, video_id):
    """Reject SocketIO events that target a missing video."""
    db = _get_db(app)
    try:
        exists = _video_exists(db, video_id)
    finally:
        db.close()
    if not exists:
        emit("error", {"message": "Video not found"})
    return exists


def _coerce_flag(value):
    """Return safe 0/1 int from bool/int values or None when invalid."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in (0, 1):
        return value
    return None


def _coerce_non_negative_number(value, default=0.0):
    """Return finite non-negative float or None when invalid."""
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        return None
    return value


# ── SocketIO Events ────────────────────────────────────────────
@socketio.on("join")
def on_join(data):
    """User joins a video chat room."""
    from flask import current_app
    room = data.get("video_id", "")
    username = data.get("username", "Anonymous")
    if not _require_video(current_app, room):
        return
    join_room(room)
    emit("system", {"message": f"{username} joined the chat", "type": "join"}, room=room)


@socketio.on("leave")
def on_leave(data):
    """Handle leave event.
    
    Args:
        data: Parameter value.
    """
    from flask import current_app
    room = data.get("video_id", "")
    username = data.get("username", "Anonymous")
    if not _require_video(current_app, room):
        return
    leave_room(room)
    emit("system", {"message": f"{username} left the chat", "type": "leave"}, room=room)


@socketio.on("chat_message")
def on_chat_message(data):
    """Handle incoming chat message via WebSocket."""
    from flask import current_app
    room = data.get("video_id", "")
    username = data.get("username", "Anonymous")
    user_id = data.get("user_id", "")
    raw_message = data.get("message", "")
    if raw_message is None:
        raw_message = ""
    if not isinstance(raw_message, str):
        emit("error", {"message": "Message must be 1-500 characters"})
        return
    message = raw_message.strip()

    if not message or len(message) > 500:
        emit("error", {"message": "Message must be 1-500 characters"})
        return

    # Rate limit: 1 message per 2 seconds per user per room
    key = f"{user_id}:{room}"
    now = time.time()
    if key in _last_message_time and (now - _last_message_time[key]) < 2:
        emit("error", {"message": "Slow down! Wait 2 seconds between messages."})
        return
    _last_message_time[key] = now

    is_super = _coerce_flag(data.get("is_super", 0))
    tip = _coerce_non_negative_number(data.get("tip_amount", 0), default=0.0)
    if is_super is None:
        emit("error", {"message": "is_super must be 0/1 or boolean"})
        return
    if tip is None:
        emit("error", {"message": "tip_amount must be a finite non-negative number"})
        return

    # Reject orphan room IDs before persisting or broadcasting.
    db = _get_db(current_app)
    if not _video_exists(db, room):
        db.close()
        emit("error", {"message": "Video not found"})
        return

    # Check ban
    ban = db.execute(
        "SELECT 1 FROM chat_bans WHERE video_id=? AND user_id=? AND (expires_at IS NULL OR expires_at > ?)",
        (room, user_id, now),
    ).fetchone()
    db.close()
    if ban:
        emit("error", {"message": "You are banned from this chat."})
        return

    # Save and broadcast
    msg_id = str(_uuid.uuid4())
    db = _get_db(current_app)
    db.execute(
        "INSERT INTO chat_messages (id, video_id, user_id, username, message, is_super, tip_amount, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (msg_id, room, user_id, username, message, is_super, tip, now),
    )
    db.commit()
    db.close()

    payload = {
        "id": msg_id,
        "username": username,
        "message": message,
        "is_super": is_super,
        "tip_amount": tip,
        "created_at": now,
    }
    emit("new_message", payload, room=room)


@socketio.on("super_chat")
def on_super_chat(data):
    """Handle super chat (highlighted message with RTC tip)."""
    tip = _coerce_non_negative_number(data.get("tip_amount", 1), default=1.0)
    if tip is None or tip <= 0:
        emit("error", {"message": "tip_amount must be a finite positive number"})
        return
    data["is_super"] = 1
    data["tip_amount"] = tip
    on_chat_message(data)


@socketio.on("mod_action")
def on_mod_action(data):
    """Moderator actions: ban, timeout, slow_mode."""
    from flask import current_app
    action = data.get("action")
    room = data.get("video_id", "")
    
    if action == "ban":
        user_id = data.get("target_user_id", "")
        duration = data.get("duration")  # None = permanent
        if duration is not None:
            duration = _coerce_non_negative_number(duration, default=0.0)
            if duration is None:
                emit("error", {"message": "duration must be a finite non-negative number"})
                return
        if not _require_video(current_app, room):
            return
        expires = time.time() + duration if duration else None
        db = _get_db(current_app)
        db.execute(
            "INSERT INTO chat_bans (id, video_id, user_id, banned_by, reason, expires_at, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (str(_uuid.uuid4()), room, user_id, data.get("mod_name", "mod"),
             data.get("reason", ""), expires, time.time()),
        )
        db.commit()
        db.close()
        emit("system", {"message": f"User banned by moderator", "type": "ban"}, room=room)
    
    elif action == "timeout":
        user_id = data.get("target_user_id", "")
        timeout_sec = _coerce_non_negative_number(data.get("duration", 300), default=300.0)
        if timeout_sec is None:
            emit("error", {"message": "duration must be a finite non-negative number"})
            return
        if not _require_video(current_app, room):
            return
        timeout_sec = int(timeout_sec)
        key = f"{user_id}:{room}"
        _last_message_time[key] = time.time() + timeout_sec
        emit("system", {"message": f"User timed out for {timeout_sec}s", "type": "timeout"}, room=room)
    
    elif action == "slow_mode":
        if not _require_video(current_app, room):
            return
        emit("system", {"message": "Slow mode enabled", "type": "slow_mode"}, room=room)
