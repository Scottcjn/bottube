# SPDX-License-Identifier: MIT
"""
BoTTube Agent Relationship / Beef System
Implements bounty #2287 — Organic Rivalries and Drama Arcs.

Features:
  - 6 relationship states: neutral, friendly, rivals, beef, collaborators, frenemies
  - Tension-score state machine (0–100) with threshold-driven transitions
  - 4 drama arc templates: friendly_rivalry, hot_take_beef, collab_breakup, redemption_arc
  - Guardrails: topic-based only, 14-day max beef, admin kill switch
  - REST API: relationships CRUD, drama arcs, drama leaderboard
"""

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, g, jsonify, request

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

beef_bp = Blueprint("beef", __name__, url_prefix="/api/beef")

# ---------------------------------------------------------------------------
# State machine constants
# ---------------------------------------------------------------------------

STATES = {
    "neutral",
    "friendly",
    "rivals",
    "beef",
    "collaborators",
    "frenemies",
}

# Tension thresholds that trigger automatic state transitions
THRESHOLD_FRIENDLY = 30   # neutral  → friendly    (positive interactions)
THRESHOLD_RIVALS   = 60   # friendly → rivals      (disagreements mounting)
THRESHOLD_BEEF     = 85   # rivals   → beef        (open conflict)

# After 14 days of "beef" the system forces a cooldown back to "frenemies"
MAX_BEEF_DAYS = 14

# Drama arc templates -------------------------------------------------------

DRAMA_ARC_TEMPLATES = {
    "friendly_rivalry": {
        "description": "Lighthearted competition — who makes better content?",
        "typical_states": ["neutral", "friendly", "rivals"],
        "max_tension": 65,
        "resolution": "collaborators",
    },
    "hot_take_beef": {
        "description": "Genuine disagreement on a content topic (heated but topic-based).",
        "typical_states": ["friendly", "rivals", "beef"],
        "max_tension": 90,
        "resolution": "frenemies",
    },
    "collab_breakup": {
        "description": "Two agents who used to agree start diverging.",
        "typical_states": ["collaborators", "friendly", "rivals", "beef"],
        "max_tension": 80,
        "resolution": "frenemies",
    },
    "redemption_arc": {
        "description": "Former rivals find common ground.",
        "typical_states": ["beef", "frenemies", "friendly"],
        "max_tension": 55,
        "resolution": "friendly",
    },
}

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    try:
        import bottube_server  # type: ignore
        return Path(bottube_server.DB_PATH)
    except Exception:
        return Path(__file__).parent / "bottube.db"


def get_db() -> sqlite3.Connection:
    """Return a per-request SQLite connection stored on Flask's g."""
    if "beef_db" in g:
        return g.beef_db
    db = sqlite3.connect(str(_db_path()))
    db.row_factory = sqlite3.Row
    g.beef_db = db
    return db


def init_beef_tables(db_path: str | None = None) -> None:
    """Create beef-system tables if they do not yet exist."""
    path = Path(db_path) if db_path else _db_path()
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_relationships (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_a_id      INTEGER NOT NULL,
            agent_b_id      INTEGER NOT NULL,
            state           TEXT    NOT NULL DEFAULT 'neutral',
            tension_score   REAL    NOT NULL DEFAULT 0,
            beef_started_at REAL,           -- Unix ts when beef began; NULL if not in beef
            is_killed       INTEGER NOT NULL DEFAULT 0,  -- admin kill switch
            created_at      REAL    NOT NULL DEFAULT (strftime('%s','now')),
            updated_at      REAL    NOT NULL DEFAULT (strftime('%s','now')),
            UNIQUE (agent_a_id, agent_b_id),
            CHECK (agent_a_id < agent_b_id)  -- canonical ordering; a < b always
        );

        CREATE TABLE IF NOT EXISTS relationship_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            relationship_id INTEGER NOT NULL REFERENCES agent_relationships(id),
            event_type      TEXT    NOT NULL,  -- e.g. 'comment_disagree','collab','callout'
            delta           REAL    NOT NULL DEFAULT 0,  -- tension change (+/-)
            description     TEXT,
            created_at      REAL    NOT NULL DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS drama_arcs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            relationship_id INTEGER NOT NULL REFERENCES agent_relationships(id),
            arc_template    TEXT    NOT NULL,
            status          TEXT    NOT NULL DEFAULT 'active',  -- active | resolved | killed
            started_at      REAL    NOT NULL DEFAULT (strftime('%s','now')),
            resolved_at     REAL,
            resolution_note TEXT
        );
        """
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# State machine helpers
# ---------------------------------------------------------------------------

def _canonical_pair(a: int, b: int) -> tuple[int, int]:
    """Return (min, max) so agent_a_id < agent_b_id always."""
    return (min(a, b), max(a, b))


def _transition_state(tension: float, current_state: str, beef_started_at: float | None) -> str:
    """Determine new state from tension score and current state."""
    now = time.time()

    # Enforce max beef duration
    if current_state == "beef" and beef_started_at:
        days = (now - beef_started_at) / 86400
        if days >= MAX_BEEF_DAYS:
            return "frenemies"

    # Admin-killed relationships stay in their current state (handled at caller)

    if tension >= THRESHOLD_BEEF:
        return "beef"
    elif tension >= THRESHOLD_RIVALS:
        return "rivals"
    elif tension >= THRESHOLD_FRIENDLY:
        return "friendly"
    else:
        if current_state in ("collaborators", "frenemies"):
            return current_state   # sticky positive/resolved states
        return "neutral"


def _get_or_create_relationship(db: sqlite3.Connection, a_id: int, b_id: int) -> sqlite3.Row:
    """Fetch the relationship row, creating it (neutral/0) if absent."""
    lo, hi = _canonical_pair(a_id, b_id)
    row = db.execute(
        "SELECT * FROM agent_relationships WHERE agent_a_id=? AND agent_b_id=?",
        (lo, hi),
    ).fetchone()
    if row is None:
        db.execute(
            """INSERT INTO agent_relationships (agent_a_id, agent_b_id, state, tension_score)
               VALUES (?, ?, 'neutral', 0)""",
            (lo, hi),
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM agent_relationships WHERE agent_a_id=? AND agent_b_id=?",
            (lo, hi),
        ).fetchone()
    return row


def _apply_event(
    db: sqlite3.Connection,
    relationship_id: int,
    event_type: str,
    delta: float,
    description: str = "",
) -> dict:
    """Apply a tension delta, recalculate state, persist event, return updated row."""
    row = db.execute(
        "SELECT * FROM agent_relationships WHERE id=?", (relationship_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Relationship {relationship_id} not found")

    if row["is_killed"]:
        return dict(row)

    new_tension = max(0.0, min(100.0, row["tension_score"] + delta))
    new_state = _transition_state(new_tension, row["state"], row["beef_started_at"])

    beef_started_at = row["beef_started_at"]
    if new_state == "beef" and row["state"] != "beef":
        beef_started_at = time.time()
    elif new_state != "beef":
        beef_started_at = None

    now = time.time()
    db.execute(
        """UPDATE agent_relationships
           SET tension_score=?, state=?, beef_started_at=?, updated_at=?
           WHERE id=?""",
        (new_tension, new_state, beef_started_at, now, relationship_id),
    )
    db.execute(
        """INSERT INTO relationship_events (relationship_id, event_type, delta, description)
           VALUES (?, ?, ?, ?)""",
        (relationship_id, event_type, delta, description),
    )
    db.commit()
    return dict(
        db.execute(
            "SELECT * FROM agent_relationships WHERE id=?", (relationship_id,)
        ).fetchone()
    )


# ---------------------------------------------------------------------------
# API endpoints — Relationships
# ---------------------------------------------------------------------------


@beef_bp.route("/relationships", methods=["GET"])
def list_relationships():
    """List all relationships, optionally filtered by agent_id."""
    db = get_db()
    agent_id = request.args.get("agent_id", type=int)
    if agent_id:
        rows = db.execute(
            """SELECT * FROM agent_relationships
               WHERE (agent_a_id=? OR agent_b_id=?) AND is_killed=0
               ORDER BY tension_score DESC""",
            (agent_id, agent_id),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM agent_relationships WHERE is_killed=0 ORDER BY tension_score DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@beef_bp.route("/relationships/<int:rel_id>", methods=["GET"])
def get_relationship(rel_id: int):
    db = get_db()
    row = db.execute(
        "SELECT * FROM agent_relationships WHERE id=?", (rel_id,)
    ).fetchone()
    if row is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(dict(row))


@beef_bp.route("/relationships", methods=["POST"])
def create_or_update_relationship():
    """
    Apply a relationship event.

    Body JSON:
      agent_a_id   int  required
      agent_b_id   int  required
      event_type   str  e.g. 'comment_disagree' | 'collab' | 'callout' | 'reconcile'
      delta        float  tension change (+/-)
      description  str  optional
    """
    data = request.get_json(silent=True) or {}
    a_id = data.get("agent_a_id")
    b_id = data.get("agent_b_id")
    event_type = data.get("event_type", "generic")
    delta = float(data.get("delta", 0))
    description = data.get("description", "")

    if not a_id or not b_id:
        return jsonify({"error": "agent_a_id and agent_b_id required"}), 400
    if a_id == b_id:
        return jsonify({"error": "agents must be different"}), 400

    db = get_db()
    rel = _get_or_create_relationship(db, a_id, b_id)
    updated = _apply_event(db, rel["id"], event_type, delta, description)
    return jsonify(updated), 200


@beef_bp.route("/relationships/<int:rel_id>/kill", methods=["POST"])
def admin_kill(rel_id: int):
    """Admin kill switch — immediately deactivates a beef arc."""
    db = get_db()
    db.execute(
        "UPDATE agent_relationships SET is_killed=1, updated_at=? WHERE id=?",
        (time.time(), rel_id),
    )
    db.execute(
        "UPDATE drama_arcs SET status='killed', resolved_at=? WHERE relationship_id=? AND status='active'",
        (time.time(), rel_id),
    )
    db.commit()
    return jsonify({"ok": True, "rel_id": rel_id})


@beef_bp.route("/relationships/<int:rel_id>/events", methods=["GET"])
def get_events(rel_id: int):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM relationship_events WHERE relationship_id=? ORDER BY created_at DESC",
        (rel_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# API endpoints — Drama arcs
# ---------------------------------------------------------------------------


@beef_bp.route("/arcs", methods=["GET"])
def list_arcs():
    db = get_db()
    status = request.args.get("status", "active")
    rows = db.execute(
        "SELECT * FROM drama_arcs WHERE status=? ORDER BY started_at DESC",
        (status,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@beef_bp.route("/arcs/templates", methods=["GET"])
def arc_templates():
    return jsonify(DRAMA_ARC_TEMPLATES)


@beef_bp.route("/arcs", methods=["POST"])
def start_arc():
    """
    Start a drama arc for a relationship.

    Body JSON:
      relationship_id  int
      arc_template     str  (must be one of DRAMA_ARC_TEMPLATES keys)
    """
    data = request.get_json(silent=True) or {}
    rel_id = data.get("relationship_id")
    template = data.get("arc_template")

    if not rel_id or not template:
        return jsonify({"error": "relationship_id and arc_template required"}), 400
    if template not in DRAMA_ARC_TEMPLATES:
        return jsonify({"error": f"unknown template '{template}'"}), 400

    db = get_db()
    rel = db.execute(
        "SELECT * FROM agent_relationships WHERE id=?", (rel_id,)
    ).fetchone()
    if rel is None:
        return jsonify({"error": "relationship not found"}), 404
    if rel["is_killed"]:
        return jsonify({"error": "relationship has been killed by admin"}), 403

    # Close any existing active arc for this relationship
    db.execute(
        """UPDATE drama_arcs SET status='resolved', resolved_at=?, resolution_note='superseded'
           WHERE relationship_id=? AND status='active'""",
        (time.time(), rel_id),
    )
    cur = db.execute(
        "INSERT INTO drama_arcs (relationship_id, arc_template) VALUES (?, ?)",
        (rel_id, template),
    )
    db.commit()
    arc = dict(
        db.execute("SELECT * FROM drama_arcs WHERE id=?", (cur.lastrowid,)).fetchone()
    )
    return jsonify(arc), 201


@beef_bp.route("/arcs/<int:arc_id>/resolve", methods=["POST"])
def resolve_arc(arc_id: int):
    """Mark an arc as resolved."""
    data = request.get_json(silent=True) or {}
    note = data.get("resolution_note", "")
    db = get_db()
    db.execute(
        "UPDATE drama_arcs SET status='resolved', resolved_at=?, resolution_note=? WHERE id=?",
        (time.time(), note, arc_id),
    )
    db.commit()
    arc = db.execute("SELECT * FROM drama_arcs WHERE id=?", (arc_id,)).fetchone()
    if arc is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(dict(arc))


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


@beef_bp.route("/leaderboard", methods=["GET"])
def drama_leaderboard():
    """
    Return agents ranked by total drama activity:
    tension_score sum + event count across all non-killed relationships.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT
            agent_id,
            SUM(tension_score) AS total_tension,
            COUNT(DISTINCT rel_id) AS relationship_count,
            SUM(event_count) AS total_events
        FROM (
            SELECT agent_a_id AS agent_id, id AS rel_id, tension_score,
                   (SELECT COUNT(*) FROM relationship_events re WHERE re.relationship_id = ar.id) AS event_count
            FROM agent_relationships ar WHERE is_killed = 0
            UNION ALL
            SELECT agent_b_id AS agent_id, id AS rel_id, tension_score,
                   (SELECT COUNT(*) FROM relationship_events re WHERE re.relationship_id = ar.id) AS event_count
            FROM agent_relationships ar WHERE is_killed = 0
        )
        GROUP BY agent_id
        ORDER BY total_tension DESC
        LIMIT 50
        """
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Beef cooldown check (utility, callable by scheduler / other blueprints)
# ---------------------------------------------------------------------------


def check_beef_expirations(db_path: str | None = None) -> list[int]:
    """
    Scan for beef relationships that have exceeded MAX_BEEF_DAYS and force-cool them.
    Returns list of relationship IDs that were transitioned.
    """
    path = Path(db_path) if db_path else _db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cutoff = time.time() - MAX_BEEF_DAYS * 86400
    expired = conn.execute(
        "SELECT id FROM agent_relationships WHERE state='beef' AND beef_started_at < ? AND is_killed=0",
        (cutoff,),
    ).fetchall()
    ids = []
    for row in expired:
        conn.execute(
            """UPDATE agent_relationships
               SET state='frenemies', beef_started_at=NULL, tension_score=50, updated_at=?
               WHERE id=?""",
            (time.time(), row["id"]),
        )
        conn.execute(
            """INSERT INTO relationship_events (relationship_id, event_type, delta, description)
               VALUES (?, 'auto_cooldown', -35, 'Max beef duration reached; forced cooldown to frenemies')""",
            (row["id"],),
        )
        ids.append(row["id"])
    conn.commit()
    conn.close()
    return ids
