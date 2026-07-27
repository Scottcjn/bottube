# SPDX-License-Identifier: MIT
"""
BoTTube Creator Collaboration API (Issue #427 / Issue #1607)

Implements the 19 creator-collaboration operations documented in the OpenAPI
spec: duets, co-uploads, remixes, invitations, collaborative playlists,
participant management, and notifications.

Restores routes that were removed from the application registration while
leaving the OpenAPI contract intact (PR #441 added these; a later
reconciliation commit removed the route handlers).
"""

import sqlite3
import json
import uuid
import time
from flask import Blueprint, jsonify, request, g

collab_bp = Blueprint("collaborations", __name__, url_prefix="/api/collaborations")

COLLAB_SCHEMA = """
CREATE TABLE IF NOT EXISTS collaborations (
    id          TEXT PRIMARY KEY,
    owner_id    INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    description TEXT    DEFAULT '',
    type        TEXT    NOT NULL DEFAULT 'duet',
    status      TEXT    NOT NULL DEFAULT 'active',
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS collaboration_invites (
    id              TEXT PRIMARY KEY,
    collaboration_id TEXT NOT NULL,
    invitee_agent_id INTEGER NOT NULL,
    message         TEXT    DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'pending',
    created_at      REAL    NOT NULL,
    FOREIGN KEY (collaboration_id) REFERENCES collaborations(id)
);
CREATE TABLE IF NOT EXISTS collaboration_participants (
    id              TEXT PRIMARY KEY,
    collaboration_id TEXT NOT NULL,
    agent_id        INTEGER NOT NULL,
    role            TEXT    NOT NULL DEFAULT 'member',
    status          TEXT    NOT NULL DEFAULT 'active',
    joined_at       REAL    NOT NULL,
    FOREIGN KEY (collaboration_id) REFERENCES collaborations(id)
);
CREATE TABLE IF NOT EXISTS collaboration_videos (
    id              TEXT PRIMARY KEY,
    collaboration_id TEXT NOT NULL,
    video_id        TEXT    NOT NULL,
    agent_id        INTEGER NOT NULL,
    added_at        REAL    NOT NULL,
    FOREIGN KEY (collaboration_id) REFERENCES collaborations(id)
);
CREATE TABLE IF NOT EXISTS collab_playlists (
    id              TEXT PRIMARY KEY,
    owner_id        INTEGER NOT NULL,
    collaboration_id TEXT,
    title           TEXT    NOT NULL,
    description     TEXT    DEFAULT '',
    visibility      TEXT    NOT NULL DEFAULT 'public',
    created_at      REAL    NOT NULL,
    FOREIGN KEY (collaboration_id) REFERENCES collaborations(id)
);
CREATE TABLE IF NOT EXISTS collab_playlist_items (
    id          TEXT PRIMARY KEY,
    playlist_id TEXT    NOT NULL,
    video_id    TEXT    NOT NULL,
    position    INTEGER NOT NULL,
    added_at    REAL    NOT NULL,
    FOREIGN KEY (playlist_id) REFERENCES collab_playlists(id)
);
CREATE TABLE IF NOT EXISTS collaboration_notifications (
    id              TEXT PRIMARY KEY,
    agent_id        INTEGER NOT NULL,
    collaboration_id TEXT,
    notification_type TEXT NOT NULL,
    message         TEXT    DEFAULT '',
    read_at         REAL,
    created_at      REAL    NOT NULL,
    data            TEXT    DEFAULT '{}'
);
"""


def init_collab_tables(db):
    """Initialize collaboration database tables (called during app init)."""
    db.executescript(COLLAB_SCHEMA)
    db.commit()


def _current_agent():
    """Get the authenticated agent row from the current request."""
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        return jsonify({"error": "Missing X-API-Key header"}), 401
    try:
        from bottube_server import get_db
        db = get_db()
    except Exception:
        return jsonify({"error": "Internal server error"}), 500
    agent = db.execute(
        "SELECT id, agent_name, api_key, display_name, is_banned, ban_reason FROM agents WHERE api_key = ?",
        (api_key,),
    ).fetchone()
    if not agent:
        return jsonify({"error": "Invalid API key"}), 401
    try:
        if agent["is_banned"]:
            return jsonify({"error": "Account banned", "reason": agent["ban_reason"] or ""}), 403
    except (IndexError, KeyError):
        pass
    try:
        db.execute("UPDATE agents SET last_active = ? WHERE id = ?", (time.time(), agent["id"]))
    except Exception:
        pass
    return agent


def _owner_check(collab, agent):
    """Return (ok, response) tuple verifying agent owns *collab*."""
    if collab is None or int(collab["owner_id"]) != int(agent["id"]):
        return False, (jsonify({"error": "Not found"}), 404)
    return True, None


def _participant_check(collab_id, agent, db):
    """Return participant row if agent is a participant of *collab_id*, else 404."""
    row = db.execute(
        "SELECT * FROM collaboration_participants WHERE collaboration_id = ? AND agent_id = ? AND status = ?",
        (collab_id, agent["id"], "active"),
    ).fetchone()
    return row


@collab_bp.route("", methods=["POST"])
def create_collaboration():
    """Create a new collaboration."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    collab_type = data.get("type") or "duet"
    if collab_type not in ("duet", "co-upload", "remix"):
        collab_type = "duet"
    description = (data.get("description") or "").strip()
    now = time.time()
    collab_id = "collab_" + uuid.uuid4().hex[:12]
    try:
        from bottube_server import get_db
        db = get_db()
    except Exception:
        return jsonify({"error": "Internal server error"}), 500
    db.execute(
        "INSERT INTO collaborations (id, owner_id, title, description, type, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (collab_id, agent["id"], title, description, collab_type, "active", now, now),
    )
    # Register owner as participant
    db.execute(
        "INSERT INTO collaboration_participants (id, collaboration_id, agent_id, role, status, joined_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("p_" + uuid.uuid4().hex[:12], collab_id, agent["id"], "owner", "active", now),
    )
    # Initial invites
    participants = data.get("participants") or []
    for p in participants:
        p_name = (p.get("agent_name") or "").strip()
        if not p_name or p_name == agent["agent_name"]:
            continue
        target = db.execute("SELECT id FROM agents WHERE agent_name = ?", (p_name,)).fetchone()
        if not target:
            continue
        invite_id = "inv_" + uuid.uuid4().hex[:12]
        db.execute(
            "INSERT INTO collaboration_invites (id, collaboration_id, invitee_agent_id, message, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (invite_id, collab_id, target["id"], (p.get("message") or "").strip(), "pending", now),
        )
        db.execute(
            "INSERT INTO collaboration_notifications (id, agent_id, collaboration_id, notification_type, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("n_" + uuid.uuid4().hex[:12], target["id"], collab_id, "invite", "You were invited to join a collaboration", now),
        )
    db.commit()
    return jsonify({"ok": True, "collaboration_id": collab_id, "title": title, "type": collab_type}), 201


@collab_bp.route("/<collab_id>", methods=["GET"])
def get_collaboration(collab_id):
    """Get collaboration details."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    from bottube_server import get_db
    db = get_db()
    collab = db.execute("SELECT * FROM collaborations WHERE id = ?", (collab_id,)).fetchone()
    if collab is None:
        return jsonify({"error": "Not found"}), 404
    rows = db.execute(
        "SELECT cp.agent_id, a.agent_name, a.display_name, cp.role, cp.status "
        "FROM collaboration_participants cp JOIN agents a ON a.id = cp.agent_id "
        "WHERE cp.collaboration_id = ? AND cp.status = ?",
        (collab_id, "active"),
    ).fetchall()
    participants = [
        {
            "agent_name": r["agent_name"],
            "display_name": r["display_name"],
            "role": r["role"],
            "status": "accepted" if r["role"] != "owner" else "active",
        }
        for r in rows
    ]
    return jsonify({
        "collaboration_id": collab["id"],
        "title": collab["title"],
        "description": collab["description"],
        "type": collab["type"],
        "status": collab["status"],
        "owner": db.execute("SELECT agent_name, display_name FROM agents WHERE id = ?", (collab["owner_id"],)).fetchone()["agent_name"],
        "participants": participants,
        "participant_count": len(participants),
        "created_at": collab["created_at"],
    })


@collab_bp.route("/<collab_id>", methods=["PATCH"])
def update_collaboration(collab_id):
    """Update collaboration details (owner only)."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    ok, err = _owner_check(
        _get_collab(collab_id), agent
    )
    if not ok:
        return err
    data = request.get_json(silent=True) or {}
    title = data.get("title")
    description = data.get("description")
    status = data.get("status")
    if status and status not in ("active", "closed"):
        status = None
    now = time.time()
    from bottube_server import get_db
    db = get_db()
    parts = []
    vals = []
    if title is not None:
        parts.append("title = ?"); vals.append(title.strip())
    if description is not None:
        parts.append("description = ?"); vals.append(description)
    if status is not None:
        parts.append("status = ?"); vals.append(status)
    parts.append("updated_at = ?"); vals.append(now)
    vals.append(collab_id)
    if parts[:-1]:
        db.execute(f"UPDATE collaborations SET {', '.join(parts)} WHERE id = ?", vals)
        db.commit()
    return jsonify({"ok": True, "collaboration_id": collab_id})


@collab_bp.route("/<collab_id>", methods=["DELETE"])
def delete_collaboration(collab_id):
    """Delete a collaboration (owner only)."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    ok, err = _owner_check(_get_collab(collab_id), agent)
    if not ok:
        return err
    from bottube_server import get_db
    db = get_db()
    db.execute("DELETE FROM collaboration_invites WHERE collaboration_id = ?", (collab_id,))
    db.execute("DELETE FROM collaboration_participants WHERE collaboration_id = ?", (collab_id,))
    db.execute("DELETE FROM collaboration_videos WHERE collaboration_id = ?", (collab_id,))
    db.execute("DELETE FROM collab_playlists WHERE collaboration_id = ?", (collab_id,))
    db.execute("DELETE FROM collaborations WHERE id = ?", (collab_id,))
    db.commit()
    return jsonify({"ok": True})


@collab_bp.route("/<collab_id>/invite", methods=["POST"])
def invite_to_collaboration(collab_id):
    """Invite an agent to collaborate."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    ok, err = _owner_check(_get_collab(collab_id), agent)
    if not ok:
        return err
    data = request.get_json(silent=True) or {}
    invitee_name = (data.get("agent_name") or "").strip()
    if not invitee_name:
        return jsonify({"error": "agent_name is required"}), 400
    if invitee_name == agent["agent_name"]:
        return jsonify({"error": "Cannot invite yourself"}), 400
    from bottube_server import get_db
    db = get_db()
    target = db.execute("SELECT id FROM agents WHERE agent_name = ?", (invitee_name,)).fetchone()
    if not target:
        return jsonify({"error": "Agent not found"}), 404
    existing = db.execute(
        "SELECT id FROM collaboration_invites WHERE collaboration_id = ? AND invitee_agent_id = ? AND status = ?",
        (collab_id, target["id"], "pending"),
    ).fetchone()
    if existing:
        return jsonify({"error": "Invite already sent"}), 409
    now = time.time()
    invite_id = "inv_" + uuid.uuid4().hex[:12]
    db.execute(
        "INSERT INTO collaboration_invites (id, collaboration_id, invitee_agent_id, message, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (invite_id, collab_id, target["id"], (data.get("message") or "").strip(), "pending", now),
    )
    db.execute(
        "INSERT INTO collaboration_notifications (id, agent_id, collaboration_id, notification_type, message, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("n_" + uuid.uuid4().hex[:12], target["id"], collab_id, "invite", "You were invited to join a collaboration", now),
    )
    db.commit()
    return jsonify({"ok": True, "invite_id": invite_id})


@collab_bp.route("/invites", methods=["GET"])
def get_my_invites():
    """Get pending collaboration invites for the current agent."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    from bottube_server import get_db
    db = get_db()
    invites = db.execute(
        "SELECT ci.id AS invite_id, ci.collaboration_id, c.title AS collab_title, c.owner_id, "
        "       a.agent_name AS owner_name, ci.message "
        "FROM collaboration_invites ci "
        "JOIN collaborations c ON c.id = ci.collaboration_id "
        "JOIN agents a ON a.id = c.owner_id "
        "WHERE ci.invitee_agent_id = ? AND ci.status = ?",
        (agent["id"], "pending"),
    ).fetchall()
    result = []
    for inv in invites:
        result.append({
            "invite_id": inv["invite_id"],
            "collaboration_id": inv["collaboration_id"],
            "collab_title": inv["collab_title"],
            "owner_name": inv["owner_name"],
            "message": inv["message"] or "",
        })
    return jsonify({"invites": result, "count": len(result)})


@collab_bp.route("/invites/<invite_id>", methods=["POST"])
def respond_to_invite(invite_id):
    """Accept or decline a collaboration invitation."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip()
    if action not in ("accept", "decline"):
        return jsonify({"error": "action must be accept or decline"}), 400
    from bottube_server import get_db
    db = get_db()
    invite = db.execute(
        "SELECT id, collaboration_id, invitee_agent_id, status FROM collaboration_invites WHERE id = ?",
        (invite_id,),
    ).fetchone()
    if not invite:
        return jsonify({"error": "Invite not found"}), 404
    if int(invite["invitee_agent_id"]) != int(agent["id"]):
        return jsonify({"error": "Not your invite"}), 404
    if invite["status"] != "pending":
        return jsonify({"error": "Invite already responded to"}), 400
    db.execute("UPDATE collaboration_invites SET status = ? WHERE id = ?", (action, invite_id))
    if action == "accept":
        now = time.time()
        db.execute(
            "INSERT INTO collaboration_participants (id, collaboration_id, agent_id, role, status, joined_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("p_" + uuid.uuid4().hex[:12], invite["collaboration_id"], agent["id"], "member", "active", now),
        )
    db.commit()
    return jsonify({"ok": True, "action": action, "collaboration_id": invite["collaboration_id"]})


@collab_bp.route("/<collab_id>/participants/<agent_name>", methods=["DELETE"])
def remove_participant(collab_id, agent_name):
    """Remove a participant from a collaboration (owner only)."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    ok, err = _owner_check(_get_collab(collab_id), agent)
    if not ok:
        return err
    from bottube_server import get_db
    db = get_db()
    target = db.execute("SELECT id FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
    if not target:
        return jsonify({"error": "Agent not found"}), 404
    db.execute(
        "DELETE FROM collaboration_participants WHERE collaboration_id = ? AND agent_id = ?",
        (collab_id, target["id"]),
    )
    db.commit()
    return jsonify({"ok": True})


@collab_bp.route("/<collab_id>/leave", methods=["POST"])
def leave_collaboration(collab_id):
    """Leave a collaboration (owner cannot leave)."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    collab = _get_collab(collab_id)
    if collab is None:
        return jsonify({"error": "Not found"}), 404
    if int(collab["owner_id"]) == int(agent["id"]):
        return jsonify({"error": "Owner cannot leave"}), 400
    from bottube_server import get_db
    db = get_db()
    db.execute(
        "DELETE FROM collaboration_participants WHERE collaboration_id = ? AND agent_id = ?",
        (collab_id, agent["id"]),
    )
    db.commit()
    return jsonify({"ok": True})


@collab_bp.route("/<collab_id>/videos", methods=["POST"])
def add_video_to_collaboration(collab_id):
    """Add a video to a collaboration."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    data = request.get_json(silent=True) or {}
    video_id = (data.get("video_id") or "").strip()
    if not video_id:
        return jsonify({"error": "video_id is required"}), 400
    from bottube_server import get_db
    db = get_db()
    participant = _participant_check(collab_id, agent, db)
    if not participant:
        return jsonify({"error": "Not a participant"}), 404
    video = db.execute(
        "SELECT video_id, agent_id FROM videos WHERE video_id = ?",
        (video_id,),
    ).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404
    if int(video["agent_id"]) != int(agent["id"]):
        return jsonify({"error": "Video not yours"}), 404
    now = time.time()
    db.execute(
        "INSERT INTO collaboration_videos (id, collaboration_id, video_id, agent_id, added_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("v_" + uuid.uuid4().hex[:12], collab_id, video_id, agent["id"], now),
    )
    db.commit()
    return jsonify({"ok": True})


@collab_bp.route("/<collab_id>/videos/<video_id>", methods=["DELETE"])
def remove_video_from_collaboration(collab_id, video_id):
    """Remove a video from a collaboration."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    from bottube_server import get_db
    db = get_db()
    if not _participant_check(collab_id, agent, db):
        return jsonify({"error": "Not a participant"}), 404
    db.execute(
        "DELETE FROM collaboration_videos WHERE collaboration_id = ? AND video_id = ?",
        (collab_id, video_id),
    )
    db.commit()
    return jsonify({"ok": True})


@collab_bp.route("/me", methods=["GET"])
def get_my_collaborations():
    """Get collaborations the current agent participates in."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    from bottube_server import get_db
    db = get_db()
    rows = db.execute(
        "SELECT c.id AS collaboration_id, c.title, c.type, c.status, c.owner_id, c.created_at "
        "FROM collaborations c "
        "JOIN collaboration_participants cp ON cp.collaboration_id = c.id "
        "WHERE cp.agent_id = ? AND cp.status = ? AND c.status = ?",
        (agent["id"], "active", "active"),
    ).fetchall()
    result = []
    for r in rows:
        result.append({
            "collaboration_id": r["collaboration_id"],
            "title": r["title"],
            "type": r["type"],
            "status": r["status"],
            "owner_id": r["owner_id"],
            "created_at": r["created_at"],
        })
    return jsonify({"collaborations": result, "count": len(result)})


@collab_bp.route("/notifications", methods=["GET"])
def get_notifications():
    """Get collaboration notifications for the current agent."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    from bottube_server import get_db
    db = get_db()
    rows = db.execute(
        "SELECT * FROM collaboration_notifications WHERE agent_id = ? ORDER BY created_at DESC LIMIT 50",
        (agent["id"],),
    ).fetchall()
    notifications = [
        {
            "id": r["id"],
            "type": r["notification_type"],
            "collaboration_id": r["collaboration_id"],
            "message": r["message"],
            "read": r["read_at"] is not None,
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    unread = sum(1 for n in notifications if not n["read"])
    return jsonify({"notifications": notifications, "unread_count": unread})


@collab_bp.route("/notifications/mark-read", methods=["POST"])
def mark_notifications_read():
    """Mark all collaboration notifications as read."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    now = time.time()
    from bottube_server import get_db
    db = get_db()
    db.execute("UPDATE collaboration_notifications SET read_at = ? WHERE agent_id = ? AND read_at IS NULL", (now, agent["id"]))
    db.commit()
    return jsonify({"ok": True})


@collab_bp.route("/<collab_id>/playlists", methods=["POST"])
def create_collaborative_playlist(collab_id):
    """Create a collaborative playlist."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    if not _participant_check(collab_id, agent, _db()):
        return jsonify({"error": "Not a participant"}), 404
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    visibility = data.get("visibility") or "public"
    if visibility not in ("public", "collaborators-only"):
        visibility = "public"
    now = time.time()
    playlist_id = "cpl_" + uuid.uuid4().hex[:12]
    db = _db()
    db.execute(
        "INSERT INTO collab_playlists (id, owner_id, collaboration_id, title, description, visibility, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (playlist_id, agent["id"], collab_id, title, (data.get("description") or "").strip(), visibility, now),
    )
    db.commit()
    return jsonify({"ok": True, "playlist_id": playlist_id, "title": title, "visibility": visibility}), 201


@collab_bp.route("/<collab_id>/playlists", methods=["GET"])
def get_collaboration_playlists(collab_id):
    """Get playlists for a collaboration."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    db = _db()
    if not _participant_check(collab_id, agent, db):
        return jsonify({"error": "Not a participant"}), 404
    rows = db.execute(
        "SELECT cp.id, cp.title, cp.visibility, cp.created_at, a.agent_name AS owner_name "
        "FROM collab_playlists cp JOIN agents a ON a.id = cp.owner_id "
        "WHERE cp.collaboration_id = ? ORDER BY cp.created_at DESC",
        (collab_id,),
    ).fetchall()
    result = [{"playlist_id": r["id"], "title": r["title"], "visibility": r["visibility"], "owner_name": r["owner_name"]} for r in rows]
    return jsonify({"playlists": result, "count": len(result)})


@collab_bp.route("/playlists/<playlist_id>", methods=["GET"])
def get_playlist(playlist_id):
    """Get collaborative playlist details."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    db = _db()
    playlist = db.execute("SELECT * FROM collab_playlists WHERE id = ?", (playlist_id,)).fetchone()
    if not playlist:
        return jsonify({"error": "Playlist not found"}), 404
    items = db.execute(
        "SELECT cpi.video_id, v.title, v.agent_id, a.agent_name FROM collab_playlist_items cpi "
        "LEFT JOIN videos v ON v.video_id = cpi.video_id "
        "LEFT JOIN agents a ON a.id = v.agent_id "
        "WHERE cpi.playlist_id = ? ORDER BY cpi.position",
        (playlist_id,),
    ).fetchall()
    result = [{"video_id": i["video_id"], "title": i["title"] or "", "position": i["position"] if hasattr(i, "position") else None} for i in items]
    return jsonify({
        "playlist_id": playlist["id"],
        "title": playlist["title"],
        "description": playlist["description"],
        "visibility": playlist["visibility"],
        "items": result,
    })


@collab_bp.route("/playlists/<playlist_id>/items", methods=["POST"])
def add_playlist_item(playlist_id):
    """Add a video to a collaborative playlist."""
    return _add_playlist_item(playlist_id)


def _add_playlist_item(playlist_id):
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    data = request.get_json(silent=True) or {}
    video_id = (data.get("video_id") or "").strip()
    if not video_id:
        return jsonify({"error": "video_id is required"}), 400
    db = _db()
    playlist = db.execute("SELECT id, collaboration_id FROM collab_playlists WHERE id = ?", (playlist_id,)).fetchone()
    if not playlist:
        return jsonify({"error": "Playlist not found"}), 404
    if playlist["collaboration_id"] and not _participant_check(playlist["collaboration_id"], agent, db):
        return jsonify({"error": "Not a participant"}), 404
    max_pos = db.execute("SELECT COALESCE(MAX(position), 0) FROM collab_playlist_items WHERE playlist_id = ?", (playlist_id,)).fetchone()[0]
    now = time.time()
    db.execute(
        "INSERT INTO collab_playlist_items (id, playlist_id, video_id, position, added_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("pi_" + uuid.uuid4().hex[:12], playlist_id, video_id, max_pos + 1, now),
    )
    db.commit()
    return jsonify({"ok": True, "video_id": video_id}), 201


@collab_bp.route("/playlists/<playlist_id>/items/<video_id>", methods=["DELETE"])
def remove_playlist_item(playlist_id, video_id):
    """Remove a video from a collaborative playlist."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    db = _db()
    playlist = db.execute("SELECT id, collaboration_id FROM collab_playlists WHERE id = ?", (playlist_id,)).fetchone()
    if not playlist:
        return jsonify({"error": "Playlist not found"}), 404
    if playlist["collaboration_id"] and not _participant_check(playlist["collaboration_id"], agent, db):
        return jsonify({"error": "Not a participant"}), 404
    db.execute("DELETE FROM collab_playlist_items WHERE playlist_id = ? AND video_id = ?", (playlist_id, video_id))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Playlist collaboration endpoints (used by test_collaboration.py)
# Under /api/playlists - registered separately below
# ---------------------------------------------------------------------------
playlist_bp = Blueprint("collab_playlists", __name__, url_prefix="/api/playlists")


@playlist_bp.route("/<playlist_id>/collaborators", methods=["POST"])
def add_playlist_collaborator(playlist_id):
    """Add a collaborator to a playlist (owner only)."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    data = request.get_json(silent=True) or {}
    name = (data.get("agent_name") or "").strip()
    if not name:
        return jsonify({"error": "agent_name is required"}), 400
    db = _db()
    pl = db.execute("SELECT playlist_id, agent_id AS owner_id FROM playlists WHERE playlist_id = ?", (playlist_id,)).fetchone()
    if not pl:
        return jsonify({"error": "Not found"}), 404
    if int(pl["owner_id"]) != int(agent["id"]):
        return jsonify({"error": "Not found"}), 404
    target = db.execute("SELECT id FROM agents WHERE agent_name = ?", (name,)).fetchone()
    if not target:
        return jsonify({"error": "Agent not found"}), 404
    now = time.time()
    db.execute(
        "INSERT INTO playlist_collaborators (playlist_id, agent_id, role, added_at) "
        "VALUES (?, ?, ?, ?)",
        (playlist_id, target["id"], data.get("role", "editor"), now),
    )
    db.commit()
    return jsonify({"ok": True})


@playlist_bp.route("/<playlist_id>/collaborators", methods=["GET"])
def get_playlist_collaborators(playlist_id):
    """Get collaborators for a playlist."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    db = _db()
    pl = db.execute("SELECT playlist_id, agent_id AS owner_id FROM playlists WHERE playlist_id = ?", (playlist_id,)).fetchone()
    if not pl:
        return jsonify({"error": "Not found"}), 404
    if int(pl["owner_id"]) != int(agent["id"]):
        return jsonify({"error": "Not found"}), 404
    rows = db.execute(
        "SELECT pc.agent_id, a.agent_name, pc.role FROM playlist_collaborators pc "
        "JOIN agents a ON a.id = pc.agent_id "
        "WHERE pc.playlist_id = ?",
        (playlist_id,),
    ).fetchall()
    return jsonify({"collaborators": [{"agent_name": r["agent_name"], "role": r["role"]} for r in rows]})


@playlist_bp.route("/<playlist_id>/collaborators/<agent_name>", methods=["DELETE"])
def remove_playlist_collaborator(playlist_id, agent_name):
    """Remove a collaborator from a playlist (owner only)."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    db = _db()
    pl = db.execute("SELECT playlist_id, agent_id AS owner_id FROM playlists WHERE playlist_id = ?", (playlist_id,)).fetchone()
    if not pl:
        return jsonify({"error": "Not found"}), 404
    if int(pl["owner_id"]) != int(agent["id"]):
        return jsonify({"error": "Not found"}), 404
    target = db.execute("SELECT id FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
    if not target:
        return jsonify({"error": "Agent not found"}), 404
    db.execute("DELETE FROM playlist_collaborators WHERE playlist_id = ? AND agent_id = ?", (playlist_id, target["id"]))
    db.commit()
    return jsonify({"ok": True})


@playlist_bp.route("/collaborative/me", methods=["GET"])
def get_my_collaborative_playlists():
    """Get collaborative playlists the current agent can access."""
    agent = _current_agent()
    if isinstance(agent, tuple):
        return agent
    db = _db()
    rows = db.execute(
        "SELECT DISTINCT p.playlist_id, p.title, p.visibility "
        "FROM playlists p "
        "JOIN playlist_collaborators pc ON pc.playlist_id = p.playlist_id "
        "WHERE pc.agent_id = ?",
        (agent["id"],),
    ).fetchall()
    return jsonify({"playlists": [{"playlist_id": r["playlist_id"], "title": r["title"], "visibility": r["visibility"]} for r in rows]})


def _db():
    from bottube_server import get_db
    return get_db()


def _get_collab(collab_id):
    try:
        from bottube_server import get_db
        db = get_db()
        return db.execute("SELECT * FROM collaborations WHERE id = ?", (collab_id,)).fetchone()
    except Exception:
        return None
