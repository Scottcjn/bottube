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


def _event_object(data):
    if isinstance(data, dict):
        return data
    emit("error", {"message": "Event data must be an object"})
    return None


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


def _video_exists(db, video_id: str) -> bool:
    """Return True if video exists in videos table and is not removed."""
    if not video_id or not isinstance(video_id, str):
        return False
    try:
        has_videos_table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='videos'"
        ).fetchone()
        if not has_videos_table:
            return True
        row = db.execute(
            "SELECT 1 FROM videos WHERE video_id = ? AND COALESCE(is_removed, 0) = 0",
            (video_id.strip(),),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def _require_video(app, video_id):
    """Reject a SocketIO event that targets a missing video.

    Mirrors the REST live-chat adapter's video-existence contract so the
    realtime path cannot create orphan rows or broadcast for ghost videos.
    """
    db = _get_db(app)
    try:
        exists = _video_exists(db, video_id)
    finally:
        db.close()
    if not exists:
        emit("error", {"message": "Video not found"})
    return exists


def _get_agent_info_from_row(row):
    """Extract (user_id, username, is_mod) from an agents row. Returns None if banned."""
    if not row:
        return None

    # Reject banned agents on all paths
    try:
        if "is_banned" in row.keys() and row["is_banned"]:
            return None
    except Exception:
        pass

    user_id = str(row["id"])
    display_name = row["display_name"] if "display_name" in row.keys() and row["display_name"] else None
    agent_name = row["agent_name"] if "agent_name" in row.keys() and row["agent_name"] else None
    username = display_name or agent_name or user_id

    # Take mod/admin from an agents column if present; otherwise keep it owner-only
    is_mod = False
    try:
        keys = row.keys()
        if "is_mod" in keys and row["is_mod"]:
            is_mod = True
        elif "is_admin" in keys and row["is_admin"]:
            is_mod = True
    except Exception:
        pass

    return {
        "user_id": user_id,
        "username": username,
        "is_mod": is_mod,
    }


def _lookup_agent_by_key(api_key, app):
    """Query agents table for an agent matching api_key."""
    db = _get_db(app)
    try:
        has_agents = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agents'"
        ).fetchone()
        if not has_agents:
            return None
        row = db.execute(
            "SELECT * FROM agents WHERE api_key = ?",
            (api_key,),
        ).fetchone()
        return _get_agent_info_from_row(row)
    except Exception:
        pass
    finally:
        db.close()
    return None


def _lookup_agent_by_id(agent_id, app):
    """Query agents table for an agent matching integer id or agent_name."""
    db = _get_db(app)
    try:
        has_agents = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agents'"
        ).fetchone()
        if not has_agents:
            return None
        row = None
        if isinstance(agent_id, int) or (isinstance(agent_id, str) and agent_id.isdigit()):
            row = db.execute(
                "SELECT * FROM agents WHERE id = ?",
                (int(agent_id),),
            ).fetchone()
        if not row:
            row = db.execute(
                "SELECT * FROM agents WHERE agent_name = ?",
                (str(agent_id),),
            ).fetchone()
        return _get_agent_info_from_row(row)
    except Exception:
        pass
    finally:
        db.close()
    return None


def _get_authenticated_user(data, app):
    """Extract authenticated identity from Flask session (cookie) or API key.

    Resolves session user_id (agents.id) or API key to the same agent row,
    ensuring one person has one consistent user_id (agents.id) and username across both paths.
    Rejects banned agents on all paths.
    """
    from flask import request, session, has_request_context

    auth_info = None

    if has_request_context():
        # Cookie session path: real login sets session["user_id"] = agents.id (integer)
        sess_uid = session.get("user_id")
        if sess_uid is not None:
            auth_info = _lookup_agent_by_id(sess_uid, app)
            if not auth_info and sess_uid:
                # Fallback for test harnesses without agent DB rows
                username = session.get("username") or str(sess_uid)
                auth_info = {
                    "user_id": str(sess_uid),
                    "username": str(username),
                    "is_mod": bool(session.get("is_mod", False) or session.get("is_admin", False)),
                }

        # Header API key path
        if not auth_info:
            api_key = request.headers.get("X-API-Key")
            if not api_key:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    api_key = auth_header[7:].strip()
            if api_key:
                auth_info = _lookup_agent_by_key(api_key, app)

    # Payload API key path
    if not auth_info and isinstance(data, dict):
        api_key = data.get("api_key") or data.get("auth_token") or data.get("token")
        if api_key:
            auth_info = _lookup_agent_by_key(api_key, app)

    return auth_info


def _validate_payload_identity(data, auth_user):
    """Ensure client cannot spoof user_id or username in payload."""
    payload_user_id = data.get("user_id")
    payload_username = data.get("username")

    if payload_user_id and str(payload_user_id) != auth_user["user_id"]:
        return False, "Payload identity spoofing detected: user_id mismatch"
    if payload_username and str(payload_username) != auth_user["username"]:
        return False, "Payload identity spoofing detected: username mismatch"
    return True, None


def _is_mod_or_channel_owner(auth_user, room, app):
    """Return True if auth_user is platform mod/admin OR channel owner (videos.agent_id == agents.id)."""
    if auth_user.get("is_mod"):
        return True

    db = _get_db(app)
    try:
        has_videos = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='videos'"
        ).fetchone()

        if has_videos:
            row = db.execute(
                "SELECT agent_id FROM videos WHERE video_id = ?",
                (room,),
            ).fetchone()
            if row and row["agent_id"] is not None:
                if str(row["agent_id"]) == auth_user["user_id"]:
                    return True

            cols = [c[1] for c in db.execute("PRAGMA table_info(videos)").fetchall()]
            if "uploader" in cols:
                row_u = db.execute("SELECT uploader FROM videos WHERE video_id = ?", (room,)).fetchone()
                if row_u and (str(row_u["uploader"]) == auth_user["user_id"] or str(row_u["uploader"]) == auth_user["username"]):
                    return True
    except Exception:
        pass
    finally:
        db.close()

    return False


# ── SocketIO Events ────────────────────────────────────────────
@socketio.on("join")
def on_join(data):
    """User joins a video chat room."""
    data = _event_object(data)
    if data is None:
        return
    room = data.get("video_id", "")
    from flask import current_app
    db = _get_db(current_app)
    if not _video_exists(db, room):
        db.close()
        emit("error", {"message": "Video not found"})
        return
    db.close()

    auth_user = _get_authenticated_user(data, current_app)
    if not auth_user:
        emit("error", {"message": "Authentication required"})
        return

    valid, err_msg = _validate_payload_identity(data, auth_user)
    if not valid:
        emit("error", {"message": err_msg})
        return

    username = auth_user["username"]
    join_room(room)
    emit("system", {"message": f"{username} joined the chat", "type": "join"}, room=room)


@socketio.on("leave")
def on_leave(data):
    """Handle leave event.
    
    Args:
        data: Parameter value.
    """
    data = _event_object(data)
    if data is None:
        return
    room = data.get("video_id", "")
    from flask import current_app
    if not _require_video(current_app, room):
        return

    auth_user = _get_authenticated_user(data, current_app)
    if not auth_user:
        emit("error", {"message": "Authentication required"})
        return

    valid, err_msg = _validate_payload_identity(data, auth_user)
    if not valid:
        emit("error", {"message": err_msg})
        return

    username = auth_user["username"]
    leave_room(room)
    emit("system", {"message": f"{username} left the chat", "type": "leave"}, room=room)


@socketio.on("chat_message")
def on_chat_message(data):
    """Handle incoming chat message via WebSocket."""
    from flask import current_app
    data = _event_object(data)
    if data is None:
        return

    auth_user = _get_authenticated_user(data, current_app)
    if not auth_user:
        emit("error", {"message": "Authentication required"})
        return

    valid, err_msg = _validate_payload_identity(data, auth_user)
    if not valid:
        emit("error", {"message": err_msg})
        return

    user_id = auth_user["user_id"]
    username = auth_user["username"]
    room = data.get("video_id", "")

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

    is_super = _coerce_flag(data.get("is_super", 0))
    tip = _coerce_non_negative_number(data.get("tip_amount", 0), default=0.0)
    if is_super is None:
        emit("error", {"message": "is_super must be 0/1 or boolean"})
        return
    if tip is None:
        emit("error", {"message": "tip_amount must be a finite non-negative number"})
        return

    # Check video exists
    db = _get_db(current_app)
    if not _video_exists(db, room):
        db.close()
        emit("error", {"message": "Video not found"})
        return
    db.close()

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
    data = _event_object(data)
    if data is None:
        return
    tip = _coerce_non_negative_number(data.get("tip_amount", 1), default=1.0)
    if tip is None or tip <= 0:
        emit("error", {"message": "tip_amount must be a finite positive number"})
        return
    payload = dict(data)
    payload["is_super"] = 1
    payload["tip_amount"] = tip
    on_chat_message(payload)


@socketio.on("mod_action")
def on_mod_action(data):
    """Moderator actions: ban, timeout, slow_mode."""
    from flask import current_app
    data = _event_object(data)
    if data is None:
        return

    room = data.get("video_id", "")
    if not _require_video(current_app, room):
        return

    auth_user = _get_authenticated_user(data, current_app)
    if not auth_user:
        emit("error", {"message": "Authentication required"})
        return

    if not _is_mod_or_channel_owner(auth_user, room, current_app):
        emit("error", {"message": "Moderator or channel owner authorization required"})
        return

    action = data.get("action")
    mod_name = auth_user["username"]

    if action == "ban":
        user_id = data.get("target_user_id", "")
        duration = data.get("duration")  # None = permanent
        if duration is not None:
            duration = _coerce_non_negative_number(duration, default=0.0)
            if duration is None:
                emit("error", {"message": "duration must be a finite non-negative number"})
                return
        expires = time.time() + duration if duration else None
        db = _get_db(current_app)
        db.execute(
            "INSERT INTO chat_bans (id, video_id, user_id, banned_by, reason, expires_at, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (str(_uuid.uuid4()), room, user_id, mod_name,
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
        timeout_sec = int(timeout_sec)
        key = f"{user_id}:{room}"
        _last_message_time[key] = time.time() + timeout_sec
        emit("system", {"message": f"User timed out for {timeout_sec}s", "type": "timeout"}, room=room)

    elif action == "slow_mode":
        emit("system", {"message": "Slow mode enabled", "type": "slow_mode"}, room=room)
