# SPDX-License-Identifier: MIT
"""
BoTTube Live Chat - SocketIO Event Handlers
Real-time WebSocket events for chat, super chat, and moderation.

Security invariant: a socket is authenticated once at connection time from a
server-side Flask session or an API-key handshake. Event payloads never choose
the caller's identity.
"""
from flask_socketio import SocketIO, emit, join_room, leave_room
import hmac
import math
import os
import sqlite3
import time
import uuid as _uuid

socketio = SocketIO()

_last_message_time = {}
_socket_identities = {}


def init_socketio(app, db_path="bottube.db", admin_key=None):
    """Attach SocketIO to the Flask app with an explicit auth boundary.

    admin_key lets the application pass the same resolved admin secret used by
    its HTTP admin surface. Admin elevation still requires a normal user/API
    identity so moderation audit rows always contain a real actor.
    """
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    app.config["CHAT_DB_PATH"] = db_path
    if admin_key is not None:
        app.config["CHAT_ADMIN_KEY"] = str(admin_key)
    elif "CHAT_ADMIN_KEY" not in app.config:
        app.config["CHAT_ADMIN_KEY"] = (
            app.config.get("BOTTUBE_ADMIN_KEY")
            or os.environ.get("BOTTUBE_ADMIN_KEY")
            or os.environ.get("RC_ADMIN_KEY")
            or ""
        )
    return socketio


def _get_db(app):
    """Open a fresh SQLite connection for SocketIO handlers."""
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


def _coerce_agent_id(value):
    """Return a positive numeric agent id or None."""
    if isinstance(value, bool):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


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
    """Reject a SocketIO event that targets a missing video."""
    db = _get_db(app)
    try:
        exists = _video_exists(db, video_id)
    finally:
        db.close()
    if not exists:
        emit("error", {"message": "Video not found"})
    return exists


def _authenticate_socket(app, auth=None):
    """Resolve a socket to a non-banned agent from trusted credentials.

    Browser clients may use the existing Flask session cookie. Agent clients
    may send an api_key in the Socket.IO connect auth object or an X-API-Key
    handshake header. Payload user_id/username fields are never credentials.
    """
    from flask import request, session

    auth = auth if isinstance(auth, dict) else {}
    session_user_id = _coerce_agent_id(session.get("user_id"))
    api_key = auth.get("api_key") or request.headers.get("X-API-Key") or ""
    if not isinstance(api_key, str):
        api_key = ""
    api_key = api_key.strip()

    if session_user_id is None and not api_key:
        return None

    db = _get_db(app)
    try:
        row = None
        if session_user_id is not None:
            row = db.execute(
                "SELECT id, agent_name FROM agents "
                "WHERE id = ? AND COALESCE(is_banned, 0) = 0",
                (session_user_id,),
            ).fetchone()
        if row is None and api_key:
            row = db.execute(
                "SELECT id, agent_name FROM agents "
                "WHERE api_key = ? AND COALESCE(is_banned, 0) = 0",
                (api_key,),
            ).fetchone()
        if row is None:
            return None
        return {"id": int(row["id"]), "username": str(row["agent_name"])}
    except sqlite3.Error:
        return None
    finally:
        db.close()


def _current_identity():
    """Return the immutable authenticated identity for the active socket."""
    from flask import request

    identity = _socket_identities.get(request.sid)
    if identity is None:
        emit("error", {"message": "Authentication required"})
    return identity


def _admin_secret(app):
    value = (
        app.config.get("CHAT_ADMIN_KEY")
        or app.config.get("BOTTUBE_ADMIN_KEY")
        or os.environ.get("BOTTUBE_ADMIN_KEY")
        or os.environ.get("RC_ADMIN_KEY")
        or ""
    )
    return str(value) if value else ""


def _has_admin_credential(app):
    """Check X-Admin-Key without accepting secrets in query parameters."""
    from flask import request

    supplied = request.headers.get("X-Admin-Key", "")
    expected = _admin_secret(app)
    if not supplied or not expected:
        return False
    return hmac.compare_digest(str(supplied), expected)


def _can_moderate(app, video_id, identity):
    """Allow moderation only to the video's creator or authenticated admin."""
    if _has_admin_credential(app):
        return True

    db = _get_db(app)
    try:
        row = db.execute(
            "SELECT agent_id FROM videos "
            "WHERE video_id = ? AND COALESCE(is_removed, 0) = 0",
            (video_id,),
        ).fetchone()
        return bool(row) and int(row["agent_id"]) == int(identity["id"])
    except (sqlite3.Error, TypeError, ValueError):
        return False
    finally:
        db.close()


@socketio.on("connect")
def on_connect(auth=None):
    """Authenticate once and bind the socket to a server-derived identity."""
    from flask import current_app, request

    identity = _authenticate_socket(current_app, auth)
    if identity is None:
        return False
    _socket_identities[request.sid] = identity
    emit(
        "authenticated",
        {"user_id": identity["id"], "username": identity["username"]},
    )
    return True


@socketio.on("disconnect")
def on_disconnect(reason=None):
    """Forget connection identity when a socket closes."""
    del reason
    from flask import request

    _socket_identities.pop(request.sid, None)


@socketio.on("join")
def on_join(data):
    """Authenticated user joins a video chat room."""
    from flask import current_app

    identity = _current_identity()
    if identity is None:
        return
    data = _event_object(data)
    if data is None:
        return
    room = data.get("video_id", "")
    db = _get_db(current_app)
    try:
        if not _video_exists(db, room):
            emit("error", {"message": "Video not found"})
            return
    finally:
        db.close()

    join_room(room)
    emit(
        "system",
        {
            "message": f"{identity['username']} joined the chat",
            "type": "join",
        },
        room=room,
    )


@socketio.on("leave")
def on_leave(data):
    """Authenticated user leaves a video chat room."""
    from flask import current_app

    identity = _current_identity()
    if identity is None:
        return
    data = _event_object(data)
    if data is None:
        return
    room = data.get("video_id", "")
    if not _require_video(current_app, room):
        return
    leave_room(room)
    emit(
        "system",
        {
            "message": f"{identity['username']} left the chat",
            "type": "leave",
        },
        room=room,
    )


@socketio.on("chat_message")
def on_chat_message(data):
    """Persist and broadcast a message under the authenticated identity."""
    from flask import current_app

    identity = _current_identity()
    if identity is None:
        return
    data = _event_object(data)
    if data is None:
        return

    room = data.get("video_id", "")
    user_id = identity["id"]
    username = identity["username"]
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
        emit(
            "error",
            {"message": "tip_amount must be a finite non-negative number"},
        )
        return

    db = _get_db(current_app)
    try:
        if not _video_exists(db, room):
            emit("error", {"message": "Video not found"})
            return
    finally:
        db.close()

    key = f"{user_id}:{room}"
    now = time.time()
    if key in _last_message_time and (now - _last_message_time[key]) < 2:
        emit(
            "error",
            {"message": "Slow down! Wait 2 seconds between messages."},
        )
        return
    _last_message_time[key] = now

    db = _get_db(current_app)
    try:
        ban = db.execute(
            "SELECT 1 FROM chat_bans "
            "WHERE video_id=? AND user_id=? "
            "AND (expires_at IS NULL OR expires_at > ?)",
            (room, user_id, now),
        ).fetchone()
    finally:
        db.close()
    if ban:
        emit("error", {"message": "You are banned from this chat."})
        return

    msg_id = str(_uuid.uuid4())
    db = _get_db(current_app)
    try:
        db.execute(
            "INSERT INTO chat_messages "
            "(id, video_id, user_id, username, message, is_super, tip_amount, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (msg_id, room, user_id, username, message, is_super, tip, now),
        )
        db.commit()
    finally:
        db.close()

    payload = {
        "id": msg_id,
        "user_id": user_id,
        "username": username,
        "message": message,
        "is_super": is_super,
        "tip_amount": tip,
        "created_at": now,
    }
    emit("new_message", payload, room=room)


@socketio.on("super_chat")
def on_super_chat(data):
    """Handle a highlighted message with RTC tip under caller identity."""
    data = _event_object(data)
    if data is None:
        return
    tip = _coerce_non_negative_number(data.get("tip_amount", 1), default=1.0)
    if tip is None or tip <= 0:
        emit(
            "error",
            {"message": "tip_amount must be a finite positive number"},
        )
        return
    payload = dict(data)
    payload["is_super"] = 1
    payload["tip_amount"] = tip
    on_chat_message(payload)


@socketio.on("mod_action")
def on_mod_action(data):
    """Owner/admin-only moderation with the real actor recorded server-side."""
    from flask import current_app

    identity = _current_identity()
    if identity is None:
        return
    data = _event_object(data)
    if data is None:
        return

    action = data.get("action")
    room = data.get("video_id", "")
    if not _require_video(current_app, room):
        return
    if not _can_moderate(current_app, room, identity):
        emit("error", {"message": "Moderator authorization required"})
        return

    if action == "ban":
        user_id = _coerce_agent_id(data.get("target_user_id"))
        if user_id is None:
            emit("error", {"message": "target_user_id must be a valid agent id"})
            return
        duration = data.get("duration")
        if duration is not None:
            duration = _coerce_non_negative_number(duration, default=0.0)
            if duration is None:
                emit(
                    "error",
                    {"message": "duration must be a finite non-negative number"},
                )
                return
        expires = time.time() + duration if duration else None
        reason = data.get("reason", "")
        if not isinstance(reason, str):
            emit("error", {"message": "reason must be a string"})
            return

        db = _get_db(current_app)
        try:
            db.execute(
                "INSERT INTO chat_bans "
                "(id, video_id, user_id, banned_by, reason, expires_at, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    str(_uuid.uuid4()),
                    room,
                    user_id,
                    identity["username"],
                    reason,
                    expires,
                    time.time(),
                ),
            )
            db.commit()
        finally:
            db.close()
        emit(
            "system",
            {"message": "User banned by moderator", "type": "ban"},
            room=room,
        )

    elif action == "timeout":
        user_id = _coerce_agent_id(data.get("target_user_id"))
        if user_id is None:
            emit("error", {"message": "target_user_id must be a valid agent id"})
            return
        timeout_sec = _coerce_non_negative_number(
            data.get("duration", 300),
            default=300.0,
        )
        if timeout_sec is None:
            emit(
                "error",
                {"message": "duration must be a finite non-negative number"},
            )
            return
        timeout_sec = int(timeout_sec)
        key = f"{user_id}:{room}"
        _last_message_time[key] = time.time() + timeout_sec
        emit(
            "system",
            {
                "message": f"User timed out for {timeout_sec}s",
                "type": "timeout",
            },
            room=room,
        )

    elif action == "slow_mode":
        emit(
            "system",
            {"message": "Slow mode enabled", "type": "slow_mode"},
            room=room,
        )

    else:
        emit("error", {"message": "Unsupported moderation action"})
