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
from pathlib import Path

import pytest

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
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_event(client, a_id, b_id, event_type, delta, description=""):
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
    import agent_relationships as ar
    assert ar._canonical_pair(5, 3) == (3, 5)
    assert ar._canonical_pair(1, 2) == (1, 2)


# ---------------------------------------------------------------------------
# 3. State transitions
# ---------------------------------------------------------------------------

def test_transition_neutral_to_friendly():
    import agent_relationships as ar
    # tension at threshold → friendly
    assert ar._transition_state(30, "neutral", None) == "friendly"


def test_transition_friendly_to_rivals():
    import agent_relationships as ar
    assert ar._transition_state(60, "friendly", None) == "rivals"


def test_transition_rivals_to_beef():
    import agent_relationships as ar
    assert ar._transition_state(85, "rivals", None) == "beef"


def test_transition_below_threshold_stays_neutral():
    import agent_relationships as ar
    assert ar._transition_state(20, "neutral", None) == "neutral"


def test_max_beef_duration_forces_frenemies():
    import agent_relationships as ar
    # beef_started_at 15 days ago → should flip to frenemies
    started = time.time() - 15 * 86400
    result = ar._transition_state(90, "beef", started)
    assert result == "frenemies"


def test_beef_within_14_days_stays_beef():
    import agent_relationships as ar
    started = time.time() - 5 * 86400
    result = ar._transition_state(90, "beef", started)
    assert result == "beef"


# ---------------------------------------------------------------------------
# 4. REST – GET /relationships (empty)
# ---------------------------------------------------------------------------

def test_list_relationships_empty(client):
    resp = client.get("/api/beef/relationships")
    assert resp.status_code == 200
    assert resp.get_json() == []


# ---------------------------------------------------------------------------
# 5. REST – POST /relationships (creates relationship)
# ---------------------------------------------------------------------------

def test_create_relationship_via_event(client):
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
    _post_event(client, 3, 4, "disagree", 30)
    _post_event(client, 3, 4, "callout", 31)
    resp = _post_event(client, 3, 4, "hot_take", 0)  # zero-delta; just fetch
    data = resp.get_json()
    assert data["state"] == "rivals"
    assert data["tension_score"] == pytest.approx(61)


def test_tension_accumulates_to_beef(client):
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
    _post_event(client, 7, 8, "collab", 5)
    rels = client.get("/api/beef/relationships").get_json()
    rel_id = rels[0]["id"]
    resp = client.get(f"/api/beef/relationships/{rel_id}")
    assert resp.status_code == 200
    assert resp.get_json()["id"] == rel_id


def test_get_relationship_not_found(client):
    resp = client.get("/api/beef/relationships/9999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. Admin kill switch
# ---------------------------------------------------------------------------

def test_admin_kill(client):
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
    resp = client.get("/api/beef/arcs/templates")
    assert resp.status_code == 200
    templates = resp.get_json()
    for key in ("friendly_rivalry", "hot_take_beef", "collab_breakup", "redemption_arc"):
        assert key in templates


# ---------------------------------------------------------------------------
# 11. Start / list drama arcs
# ---------------------------------------------------------------------------

def test_start_drama_arc(client):
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


def test_list_active_arcs(client):
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
    _post_event(client, 17, 18, "disagree", 70)
    rels = client.get("/api/beef/relationships").get_json()
    rel_id = next(r["id"] for r in rels if r["agent_a_id"] == 17)
    arc = client.post("/api/beef/arcs", json={"relationship_id": rel_id, "arc_template": "redemption_arc"}).get_json()

    resp = client.post(f"/api/beef/arcs/{arc['id']}/resolve", json={"resolution_note": "peace achieved"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "resolved"


# ---------------------------------------------------------------------------
# 13. Leaderboard
# ---------------------------------------------------------------------------

def test_drama_leaderboard(client):
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
    resp = client.post("/api/beef/relationships", json={"event_type": "test", "delta": 5})
    assert resp.status_code == 400


def test_same_agent_returns_400(client):
    resp = _post_event(client, 99, 99, "self_hate", 10)
    assert resp.status_code == 400


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
