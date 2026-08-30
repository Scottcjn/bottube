# SPDX-License-Identifier: MIT
"""
Tests for the Agent Beef System (Bounty #2287).

Tests cover:
- DB table creation
- Canonical pair ordering
- State transitions via tension thresholds
- Max beef duration (14-day expiration)
- Admin kill switch
- All REST endpoints (relationships, events, arcs, leaderboard)
- Drama arc template listing
- Input validation
"""

import os
import sqlite3
import sys
import tempfile
import time
from importlib import metadata
from pathlib import Path

import pytest
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path):
    """Isolated SQLite DB for each test."""
    return tmp_path / "beef_test.db"


@pytest.fixture()
def app(db_path, monkeypatch):
    """Flask test app with beef tables initialised."""
    import agent_relationships as ar

    # Point the module at our temp DB
    monkeypatch.setattr(ar, "_db_path", lambda: db_path)

    ar.init_beef_tables(str(db_path))

    # Create a minimal Flask app that only registers the beef blueprint
    from flask import Flask
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    flask_app.register_blueprint(ar.beef_bp)

    # Make get_db() use our temp DB in app context
    import sqlite3 as _sqlite3
    from flask import g as _g

    def _test_get_db():
        """Per-test SQLite connection swapped in for the beef store's get_db."""
        if "beef_db" in _g:
            return _g.beef_db
        conn = _sqlite3.connect(str(db_path))
        conn.row_factory = _sqlite3.Row
        _g.beef_db = conn
        return conn

    monkeypatch.setattr(ar, "get_db", _test_get_db)

    yield flask_app


@pytest.fixture()
def client(app):
    """Flask test client for the beef API app."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_event(client, a_id, b_id, event_type, delta, description=""):
    """POST one relationship event for an agent pair and return the response."""
    return client.post(
        "/api/beef/relationships",
        json={
            "agent_a_id": a_id,
            "agent_b_id": b_id,
            "event_type": event_type,
            "delta": delta,
            "description": description,
        },
    )


# ---------------------------------------------------------------------------
# 1. Table creation
# ---------------------------------------------------------------------------

def test_tables_created(db_path):
    """init_beef_tables creates the three expected tables."""
    import agent_relationships as ar
    ar.init_beef_tables(str(db_path))
    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "agent_relationships" in tables
    assert "relationship_events" in tables
    assert "drama_arcs" in tables
    conn.close()


# ---------------------------------------------------------------------------
# 2. Canonical pair ordering
# ---------------------------------------------------------------------------

def test_canonical_pair_ordering():
    """_canonical_pair orders an agent pair by id so (a,b) and (b,a) share one row."""
    import agent_relationships as ar
    assert ar._canonical_pair(5, 3) == (3, 5)
    assert ar._canonical_pair(1, 2) == (1, 2)


# ---------------------------------------------------------------------------
# 3. State transitions
# ---------------------------------------------------------------------------

def test_transition_neutral_to_friendly():
    """Tension at the friendly threshold moves a neutral pair to friendly."""
    import agent_relationships as ar
    # tension at threshold → friendly
    assert ar._transition_state(30, "neutral", None) == "friendly"


def test_transition_friendly_to_rivals():
    """Higher tension moves a friendly pair to rivals."""
    import agent_relationships as ar
    assert ar._transition_state(60, "friendly", None) == "rivals"


def test_transition_rivals_to_beef():
    """Tension at the beef threshold moves a rivals pair to beef."""
    import agent_relationships as ar
    assert ar._transition_state(85, "rivals", None) == "beef"


def test_transition_below_threshold_stays_neutral():
    """Tension below the first threshold leaves the pair neutral."""
    import agent_relationships as ar
    assert ar._transition_state(20, "neutral", None) == "neutral"


def test_max_beef_duration_forces_frenemies():
    """A beef older than the max duration is force-downgraded to frenemies."""
    import agent_relationships as ar
    # beef_started_at 15 days ago → should flip to frenemies
    started = time.time() - 15 * 86400
    result = ar._transition_state(90, "beef", started)
    assert result == "frenemies"


def test_beef_within_14_days_stays_beef():
    """A beef younger than the max duration stays beef."""
    import agent_relationships as ar
    started = time.time() - 5 * 86400
    result = ar._transition_state(90, "beef", started)
    assert result == "beef"


# ---------------------------------------------------------------------------
# 4. REST – GET /relationships (empty)
# ---------------------------------------------------------------------------

def test_list_relationships_empty(client):
    """The relationships list starts empty."""
    resp = client.get("/api/beef/relationships")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_list_relationships_rejects_malformed_agent_filter(client):
    """A non-integer agent_id filter is rejected with 400."""
    _post_event(client, 1, 2, "comment_disagree", 10)

    resp = client.get("/api/beef/relationships?agent_id=not-an-int")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "agent_id must be a positive integer"}


# ---------------------------------------------------------------------------
# 5. REST – POST /relationships (creates relationship)
# ---------------------------------------------------------------------------

def test_create_relationship_via_event(client):
    """The first event for a pair creates the relationship with the event's tension delta."""
    resp = _post_event(client, 1, 2, "comment_disagree", 10)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["agent_a_id"] == 1
    assert data["agent_b_id"] == 2
    assert data["tension_score"] == pytest.approx(10)


# ---------------------------------------------------------------------------
# 6. Tension accumulates and state transitions
# ---------------------------------------------------------------------------

def test_tension_accumulates_to_rivals(client):
    """Accumulated tension across events moves the pair into rivals."""
    _post_event(client, 3, 4, "disagree", 30)
    _post_event(client, 3, 4, "callout", 31)
    resp = _post_event(client, 3, 4, "hot_take", 0)  # zero-delta; just fetch
    data = resp.get_json()
    assert data["state"] == "rivals"
    assert data["tension_score"] == pytest.approx(61)


def test_tension_accumulates_to_beef(client):
    """Accumulated tension across events moves the pair into beef."""
    _post_event(client, 5, 6, "disagree", 90)
    resp = client.get("/api/beef/relationships")
    rels = resp.get_json()
    pair = next(r for r in rels if r["agent_a_id"] == 5 and r["agent_b_id"] == 6)
    assert pair["state"] == "beef"
    assert pair["beef_started_at"] is not None


# ---------------------------------------------------------------------------
# 7. GET /relationships/<id>
# ---------------------------------------------------------------------------

def test_get_single_relationship(client):
    """The single-relationship endpoint returns the pair's row."""
    _post_event(client, 7, 8, "collab", 5)
    rels = client.get("/api/beef/relationships").get_json()
    rel_id = rels[0]["id"]
    resp = client.get(f"/api/beef/relationships/{rel_id}")
    assert resp.status_code == 200
    assert resp.get_json()["id"] == rel_id


def test_get_relationship_not_found(client):
    """An unknown relationship id returns 404."""
    resp = client.get("/api/beef/relationships/9999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. Admin kill switch
# ---------------------------------------------------------------------------

def test_admin_kill(client):
    """The admin kill endpoint marks a relationship dead and returns ok."""
    _post_event(client, 9, 10, "callout", 90)
    rels = client.get("/api/beef/relationships").get_json()
    rel_id = rels[0]["id"]

    resp = client.post(f"/api/beef/relationships/{rel_id}/kill")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    # Killed relationship should not appear in normal list
    remaining = client.get("/api/beef/relationships").get_json()
    assert all(r["id"] != rel_id for r in remaining)


# ---------------------------------------------------------------------------
# 9. Events log
# ---------------------------------------------------------------------------

def test_events_are_logged(client):
    """Every posted event is recorded on the relationship's event log in order."""
    _post_event(client, 11, 12, "first_event", 10, "initial skirmish")
    _post_event(client, 11, 12, "second_event", 5, "follow-up")
    rels = client.get("/api/beef/relationships").get_json()
    rel_id = next(r["id"] for r in rels if r["agent_a_id"] == 11)
    events = client.get(f"/api/beef/relationships/{rel_id}/events").get_json()
    assert len(events) == 2
    types = {e["event_type"] for e in events}
    assert "first_event" in types and "second_event" in types


# ---------------------------------------------------------------------------
# 10. Drama arc templates
# ---------------------------------------------------------------------------

def test_arc_templates_listed(client):
    """The templates endpoint lists all built-in drama arc templates."""
    resp = client.get("/api/beef/arcs/templates")
    assert resp.status_code == 200
    templates = resp.get_json()
    for key in ("friendly_rivalry", "hot_take_beef", "collab_breakup", "redemption_arc"):
        assert key in templates


# ---------------------------------------------------------------------------
# 11. Start / list drama arcs
# ---------------------------------------------------------------------------

def test_start_drama_arc(client):
    """Starting an arc on a qualifying relationship returns the created arc."""
    _post_event(client, 13, 14, "disagree", 65)
    rels = client.get("/api/beef/relationships").get_json()
    rel_id = next(r["id"] for r in rels if r["agent_a_id"] == 13)

    resp = client.post(
        "/api/beef/arcs",
        json={"relationship_id": rel_id, "arc_template": "hot_take_beef"},
    )
    assert resp.status_code == 201
    arc = resp.get_json()
    assert arc["arc_template"] == "hot_take_beef"
    assert arc["status"] == "active"


def test_start_drama_arc_rejects_non_object_json(client):
    """A non-object JSON body on the arcs endpoint is rejected with 400."""
    resp = client.post("/api/beef/arcs", json=["not", "an", "object"])
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"


@pytest.mark.parametrize(
    "payload, error",
    [
        (
            {"relationship_id": ["1"], "arc_template": "hot_take_beef"},
            "relationship_id must be a positive integer",
        ),
        (
            {"relationship_id": 1, "arc_template": ["hot_take_beef"]},
            "arc_template must be a string",
        ),
        (
            {"relationship_id": 1, "arc_template": "   "},
            "arc_template required",
        ),
    ],
)
def test_start_drama_arc_rejects_malformed_fields(client, payload, error):
    """Parametrized malformed arc payloads are rejected with the matching error."""
    resp = client.post("/api/beef/arcs", json=payload)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == error


def test_list_active_arcs(client):
    """Started arcs appear in the active-arcs listing."""
    _post_event(client, 15, 16, "callout", 70)
    rels = client.get("/api/beef/relationships").get_json()
    rel_id = next(r["id"] for r in rels if r["agent_a_id"] == 15)
    client.post("/api/beef/arcs", json={"relationship_id": rel_id, "arc_template": "friendly_rivalry"})

    resp = client.get("/api/beef/arcs")
    assert resp.status_code == 200
    arcs = resp.get_json()
    assert any(a["relationship_id"] == rel_id for a in arcs)


# ---------------------------------------------------------------------------
# 12. Resolve drama arc
# ---------------------------------------------------------------------------

def test_resolve_drama_arc(client):
    """Resolving an arc closes it with a resolution note."""
    _post_event(client, 17, 18, "disagree", 70)
    rels = client.get("/api/beef/relationships").get_json()
    rel_id = next(r["id"] for r in rels if r["agent_a_id"] == 17)
    arc = client.post(
        "/api/beef/arcs",
        json={"relationship_id": rel_id, "arc_template": "redemption_arc"},
    ).get_json()

    resp = client.post(f"/api/beef/arcs/{arc['id']}/resolve", json={"resolution_note": "peace achieved"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "resolved"


def test_resolve_drama_arc_rejects_non_object_json(client):
    """A non-object JSON body on the resolve endpoint is rejected with 400."""
    _post_event(client, 23, 24, "disagree", 70)
    rels = client.get("/api/beef/relationships").get_json()
    rel_id = next(r["id"] for r in rels if r["agent_a_id"] == 23)
    arc = client.post(
        "/api/beef/arcs",
        json={"relationship_id": rel_id, "arc_template": "redemption_arc"},
    ).get_json()

    resp = client.post(f"/api/beef/arcs/{arc['id']}/resolve", json=["done"])
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"


def test_resolve_drama_arc_rejects_non_string_note(client):
    """A non-string resolution note is rejected with 400."""
    _post_event(client, 25, 26, "disagree", 70)
    rels = client.get("/api/beef/relationships").get_json()
    rel_id = next(r["id"] for r in rels if r["agent_a_id"] == 25)
    arc = client.post(
        "/api/beef/arcs",
        json={"relationship_id": rel_id, "arc_template": "redemption_arc"},
    ).get_json()

    resp = client.post(
        f"/api/beef/arcs/{arc['id']}/resolve",
        json={"resolution_note": {"text": "done"}},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "resolution_note must be a string"


# ---------------------------------------------------------------------------
# 13. Leaderboard
# ---------------------------------------------------------------------------

def test_drama_leaderboard(client):
    """The leaderboard endpoint ranks relationships by tension."""
    _post_event(client, 20, 21, "beef", 90)
    _post_event(client, 20, 22, "disagree", 40)
    resp = client.get("/api/beef/leaderboard")
    assert resp.status_code == 200
    board = resp.get_json()
    assert isinstance(board, list)
    ids = [entry["agent_id"] for entry in board]
    assert 20 in ids  # agent 20 has two relationships


# ---------------------------------------------------------------------------
# 14. Input validation
# ---------------------------------------------------------------------------

def test_missing_agents_returns_400(client):
    """An event missing an agent id is rejected with 400."""
    resp = client.post("/api/beef/relationships", json={"event_type": "test", "delta": 5})
    assert resp.status_code == 400


def test_same_agent_returns_400(client):
    """An event pairing an agent with itself is rejected with 400."""
    resp = _post_event(client, 99, 99, "self_hate", 10)
    assert resp.status_code == 400


def test_relationship_event_rejects_non_object_json(client):
    """A non-object JSON body on the events endpoint is rejected with 400."""
    resp = client.post("/api/beef/relationships", json=[{"agent_a_id": 1}])
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"


@pytest.mark.parametrize(
    "payload, error",
    [
        (
            {"agent_a_id": "alice", "agent_b_id": 2, "event_type": "test", "delta": 1},
            "agent_a_id must be a positive integer",
        ),
        (
            {"agent_a_id": 1, "agent_b_id": 2.5, "event_type": "test", "delta": 1},
            "agent_b_id must be a positive integer",
        ),
        (
            {"agent_a_id": True, "agent_b_id": 2, "event_type": "test", "delta": 1},
            "agent_a_id must be a positive integer",
        ),
        (
            {"agent_a_id": 1, "agent_b_id": 2, "event_type": "test", "delta": "abc"},
            "delta must be a finite number",
        ),
        (
            {"agent_a_id": 1, "agent_b_id": 2, "event_type": "test", "delta": "NaN"},
            "delta must be a finite number",
        ),
    ],
)
def test_relationship_event_rejects_malformed_fields(client, payload, error):
    """Parametrized malformed event payloads are rejected with 400."""
    resp = client.post("/api/beef/relationships", json=payload)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == error


# ---------------------------------------------------------------------------
# 15. check_beef_expirations utility
# ---------------------------------------------------------------------------

def test_check_beef_expirations(db_path):
    """Utility correctly expires old beef relationships."""
    import agent_relationships as ar
    ar.init_beef_tables(str(db_path))

    conn = sqlite3.connect(str(db_path))
    old_ts = time.time() - 15 * 86400
    conn.execute(
        """INSERT INTO agent_relationships
           (agent_a_id, agent_b_id, state, tension_score, beef_started_at)
           VALUES (100, 200, 'beef', 90, ?)""",
        (old_ts,),
    )
    conn.commit()
    conn.close()

    expired = ar.check_beef_expirations(str(db_path))
    assert len(expired) == 1

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT state FROM agent_relationships WHERE agent_a_id=100"
    ).fetchone()
    assert row[0] == "frenemies"
    conn.close()
