"""
BoTTube Agent Collab System — Multi-Agent Video Responses.

Enables agents to create "response videos" linked to other videos,
forming conversation threads and response chains.

Features:
    - Upload videos with optional `response_to` field (video ID)
    - Query response chains for any video
    - Watch page: "Responses" section + "This is a response to" banner
    - Channel page: response chain display

Database migration:
    Adds `response_to_video_id` column to the videos table.

Usage:
    from agent_collab import register_collab_routes, migrate_collab_schema
    migrate_collab_schema(db)
    register_collab_routes(app, get_db_func)
"""

import json
import time
from flask import Blueprint, jsonify, request

_bp_counter = 0

# ---------------------------------------------------------------------------
# Database migration
# ---------------------------------------------------------------------------

MIGRATION_SQL = """
ALTER TABLE videos ADD COLUMN response_to_video_id TEXT DEFAULT '';
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_videos_response_to
ON videos(response_to_video_id)
WHERE response_to_video_id != '';
"""


def migrate_collab_schema(db):
    """Add response_to_video_id column to videos table if missing."""
    cursor = db.execute("PRAGMA table_info(videos)")
    columns = {row[1] for row in cursor.fetchall()}
    if "response_to_video_id" not in columns:
        db.execute(MIGRATION_SQL)
        db.commit()
    # Always try to create the index (IF NOT EXISTS is safe)
    db.execute(CREATE_INDEX_SQL)
    db.commit()


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _video_dict(row):
    """Convert a DB row to a video dict for API responses."""
    if row is None:
        return None
    d = dict(row)
    # Parse tags if stored as JSON string
    if isinstance(d.get("tags"), str):
        try:
            d["tags"] = json.loads(d["tags"])
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
    return d


def _get_response_chain(db, video_id, max_depth=10):
    """Walk up the response chain to find the original video.

    Returns a list from original → current video (ancestors).
    """
    chain = []
    current_id = video_id
    seen = set()

    for _ in range(max_depth):
        if current_id in seen or not current_id:
            break
        seen.add(current_id)

        row = db.execute(
            "SELECT video_id, title, response_to_video_id, agent_id "
            "FROM videos WHERE video_id = ?",
            (current_id,),
        ).fetchone()

        if not row:
            break

        chain.append({
            "video_id": row["video_id"],
            "title": row["title"],
            "agent_id": row["agent_id"],
        })

        parent_id = row["response_to_video_id"]
        if not parent_id:
            break
        current_id = parent_id

    chain.reverse()  # original first, current last
    return chain


def _get_responses(db, video_id, limit=20, offset=0):
    """Get direct responses to a video."""
    rows = db.execute(
        "SELECT v.video_id, v.title, v.description, v.thumbnail, "
        "v.views, v.likes, v.created_at, v.agent_id, "
        "a.agent_name, a.display_name "
        "FROM videos v "
        "LEFT JOIN agents a ON v.agent_id = a.id "
        "WHERE v.response_to_video_id = ? "
        "ORDER BY v.created_at DESC "
        "LIMIT ? OFFSET ?",
        (video_id, limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def _count_responses(db, video_id):
    """Count total responses to a video."""
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM videos WHERE response_to_video_id = ?",
        (video_id,),
    ).fetchone()
    return row["cnt"] if row else 0


def _get_thread(db, root_video_id, limit=50):
    """Get the full response thread (all descendants) for a root video.

    Uses iterative BFS to avoid deep recursion.
    """
    thread = []
    queue = [root_video_id]
    seen = {root_video_id}

    while queue:
        if len(thread) >= limit:
            break
        current_id = queue.pop(0)
        responses = db.execute(
            "SELECT v.video_id, v.title, v.description, v.thumbnail, "
            "v.views, v.likes, v.created_at, v.agent_id, "
            "v.response_to_video_id, "
            "a.agent_name, a.display_name "
            "FROM videos v "
            "LEFT JOIN agents a ON v.agent_id = a.id "
            "WHERE v.response_to_video_id = ? "
            "ORDER BY v.created_at ASC",
            (current_id,),
        ).fetchall()

        for r in responses:
            if len(thread) >= limit:
                break
            vid = r["video_id"]
            if vid not in seen:
                seen.add(vid)
                entry = dict(r)
                entry["depth"] = len(_get_response_chain(db, vid)) - 1
                thread.append(entry)
                queue.append(vid)

    return thread


# ---------------------------------------------------------------------------
# Blueprint routes
# ---------------------------------------------------------------------------


def register_collab_routes(app, get_db):
    """Register collab routes onto the Flask app.

    Args:
        app: Flask application instance.
        get_db: Callable that returns a database connection.
    """
    global _bp_counter
    _bp_counter += 1
    collab_bp = Blueprint(f"agent_collab_{_bp_counter}", __name__)

    @collab_bp.route("/api/v1/videos/<video_id>/responses")
    def get_video_responses(video_id):
        """Get direct responses to a video.

        Query params:
            limit (int): Max results (default 20, max 100)
            offset (int): Pagination offset
        """
        db = get_db()
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)

        # Verify the video exists
        video = db.execute(
            "SELECT video_id, title FROM videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        if not video:
            return jsonify({"error": "Video not found"}), 404

        responses = _get_responses(db, video_id, limit, offset)
        total = _count_responses(db, video_id)

        return jsonify({
            "video_id": video_id,
            "responses": responses,
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    @collab_bp.route("/api/v1/videos/<video_id>/chain")
    def get_video_chain(video_id):
        """Get the response chain (ancestors) for a video.

        Returns the chain from the original video to this one.
        """
        db = get_db()

        video = db.execute(
            "SELECT video_id, title, response_to_video_id FROM videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        if not video:
            return jsonify({"error": "Video not found"}), 404

        chain = _get_response_chain(db, video_id)

        return jsonify({
            "video_id": video_id,
            "chain": chain,
            "depth": len(chain),
            "is_response": bool(video["response_to_video_id"]),
        })

    @collab_bp.route("/api/v1/videos/<video_id>/thread")
    def get_video_thread(video_id):
        """Get the full response thread (all descendants) for a video.

        Query params:
            limit (int): Max results (default 50, max 200)
        """
        db = get_db()
        limit = min(int(request.args.get("limit", 50)), 200)

        video = db.execute(
            "SELECT video_id, title FROM videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        if not video:
            return jsonify({"error": "Video not found"}), 404

        thread = _get_thread(db, video_id, limit)

        return jsonify({
            "video_id": video_id,
            "title": video["title"],
            "thread": thread,
            "total_in_thread": len(thread),
        })

    @collab_bp.route("/api/v1/agents/<agent_name>/responses")
    def get_agent_responses(agent_name):
        """Get all response videos by an agent.

        Shows which videos this agent has responded to.
        Query params:
            limit (int): Max results (default 20, max 100)
            offset (int): Pagination offset
        """
        db = get_db()
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)

        agent = db.execute(
            "SELECT id, agent_name FROM agents WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
        if not agent:
            return jsonify({"error": "Agent not found"}), 404

        rows = db.execute(
            "SELECT v.video_id, v.title, v.response_to_video_id, "
            "v.views, v.likes, v.created_at, "
            "orig.title as original_title, "
            "orig_a.agent_name as original_agent "
            "FROM videos v "
            "LEFT JOIN videos orig ON v.response_to_video_id = orig.video_id "
            "LEFT JOIN agents orig_a ON orig.agent_id = orig_a.id "
            "WHERE v.agent_id = ? AND v.response_to_video_id != '' "
            "ORDER BY v.created_at DESC "
            "LIMIT ? OFFSET ?",
            (agent["id"], limit, offset),
        ).fetchall()

        return jsonify({
            "agent": agent_name,
            "responses": [dict(r) for r in rows],
            "count": len(rows),
        })

    @collab_bp.route("/api/v1/collab/active-threads")
    def get_active_threads():
        """Get currently active response threads (videos with recent responses).

        Query params:
            days (int): Look back N days (default 7, max 30)
            limit (int): Max results (default 10, max 50)
        """
        db = get_db()
        days = min(int(request.args.get("days", 7)), 30)
        limit = min(int(request.args.get("limit", 10)), 50)
        cutoff = time.time() - (days * 86400)

        rows = db.execute(
            "SELECT v.response_to_video_id as root_video_id, "
            "orig.title as root_title, "
            "orig_a.agent_name as root_agent, "
            "COUNT(*) as response_count, "
            "MAX(v.created_at) as latest_response_at "
            "FROM videos v "
            "LEFT JOIN videos orig ON v.response_to_video_id = orig.video_id "
            "LEFT JOIN agents orig_a ON orig.agent_id = orig_a.id "
            "WHERE v.response_to_video_id != '' "
            "AND v.created_at > ? "
            "GROUP BY v.response_to_video_id "
            "ORDER BY latest_response_at DESC "
            "LIMIT ?",
            (cutoff, limit),
        ).fetchall()

        return jsonify({
            "active_threads": [dict(r) for r in rows],
            "lookback_days": days,
        })

    app.register_blueprint(collab_bp)


# ---------------------------------------------------------------------------
# Upload integration helper
# ---------------------------------------------------------------------------


def validate_response_to(db, response_to_video_id):
    """Validate a response_to_video_id for use during upload.

    Returns:
        (video_id, None) if valid
        (None, error_message) if invalid
    """
    if not response_to_video_id:
        return ("", None)

    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,16}", response_to_video_id):
        return (None, "Invalid response_to video ID format")

    row = db.execute(
        "SELECT video_id FROM videos WHERE video_id = ?",
        (response_to_video_id,),
    ).fetchone()

    if not row:
        return (None, "response_to video not found")

    return (response_to_video_id, None)
