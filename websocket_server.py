"""
BoTTube Live Chat - SocketIO Event Handlers
Real-time WebSocket events for chat, super chat, and moderation.
Integrates with Flask-SocketIO.
"""
from flask_socketio import SocketIO, emit, join_room, leave_room
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


# ── SocketIO Events ────────────────────────────────────────────
@socketio.on("join")
def on_join(data):
    """User joins a video chat room."""
    room = data.get("video_id", "")
    username = data.get("username", "Anonymous")
    join_room(room)
    emit("system", {"message": f"{username} joined the chat", "type": "join"}, room=room)


@socketio.on("leave")
def on_leave(data):
    room = data.get("video_id", "")
    username = data.get("username", "Anonymous")
    leave_room(room)
    emit("system", {"message": f"{username} left the chat", "type": "leave"}, room=room)


@socketio.on("chat_message")
def on_chat_message(data):
    """Handle incoming chat message via WebSocket."""
    from flask import current_app
    room = data.get("video_id", "")
    username = data.get("username", "Anonymous")
    user_id = data.get("user_id", "")
    message = (data.get("message") or "").strip()

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

    # Check ban
    db = _get_db(current_app)
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
    is_super = int(data.get("is_super", 0))
    tip = float(data.get("tip_amount", 0))

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
    data["is_super"] = 1
    data["tip_amount"] = float(data.get("tip_amount", 1))
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
        timeout_sec = int(data.get("duration", 300))
        key = f"{user_id}:{room}"
        _last_message_time[key] = time.time() + timeout_sec
        emit("system", {"message": f"User timed out for {timeout_sec}s", "type": "timeout"}, room=room)
    
    elif action == "slow_mode":
        emit("system", {"message": "Slow mode enabled", "type": "slow_mode"}, room=room)
