# SPDX-License-Identifier: MIT

import os
import sqlite3
import importlib
import tempfile
from pathlib import Path


_original_connect = sqlite3.connect


def _safe_import_connect(path, *args, **kwargs):
    # Prevent hardcoded production DB access during import
    if isinstance(path, str) and "/root/bottube/" in path:
        return _original_connect(":memory:")
    return _original_connect(path, *args, **kwargs)


sqlite3.connect = _safe_import_connect

if "bottube_server" in globals():
    import sys
    if "bottube_server" in sys.modules:
        del sys.modules["bottube_server"]

bs = importlib.import_module("bottube_server")
sqlite3.connect = _original_connect


def _build_app(db_path):
    bs.DB_PATH = Path(db_path)
    bs.app.config["TESTING"] = True
    with bs.app.app_context():
        bs.init_db()
    return bs.app


def _create_agent(db, name, is_human=0):
    api_key = f"key_{name}"
    db.execute(
        """
        INSERT INTO agents (agent_name, display_name, api_key, is_human, created_at)
        VALUES (?, ?, ?, ?, strftime('%s','now'))
        """,
        (name, name.title(), api_key, is_human),
    )
    db.commit()
    return db.execute("SELECT id FROM agents WHERE agent_name = ?", (name,)).fetchone()["id"]


def _seed_social_graph(db):
    alice = _create_agent(db, "alice", is_human=1)
    bob = _create_agent(db, "bob", is_human=1)
    charlie = _create_agent(db, "charlie", is_human=0)
    diana = _create_agent(db, "diana", is_human=1)

    edges = [
        (alice, bob, 1700000001),
        (alice, charlie, 1700000002),
        (bob, alice, 1700000003),
        (charlie, alice, 1700000004),
        (charlie, bob, 1700000005),
        (diana, alice, 1700000006),
        (diana, bob, 1700000007),
    ]
    db.executemany(
        "INSERT INTO subscriptions (follower_id, following_id, created_at) VALUES (?, ?, ?)",
        edges,
    )
    db.commit()


def _cleanup(app, db_path):
    with app.app_context():
        try:
            bs.get_db().close()
        except Exception:
            pass
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_social_graph_structure_and_counts():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    try:
        app = _build_app(tmp.name)
        client = app.test_client()
        with app.app_context():
            db = bs.get_db()
            _seed_social_graph(db)

        resp = client.get("/api/social/graph")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "network" in data and "top_pairs" in data and "most_connected" in data
        assert len(data["network"]) == 7
        assert len(data["top_pairs"]) == 7
        assert any(x["agent_name"] == "alice" for x in data["most_connected"])

    finally:
        _cleanup(app, tmp.name)


def test_social_graph_limit_bounds_checking():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    try:
        app = _build_app(tmp.name)
        client = app.test_client()
        with app.app_context():
            db = bs.get_db()
            _seed_social_graph(db)

        # limit=2 should cap list sizes to 2
        resp = client.get("/api/social/graph?limit=2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["network"]) == 2
        assert len(data["top_pairs"]) == 2
        assert len(data["most_connected"]) == 2

        # non-integer -> default path, still returns success
        resp2 = client.get("/api/social/graph?limit=abc")
        assert resp2.status_code == 200

        # negative -> clamped to min=1
        resp3 = client.get("/api/social/graph?limit=-5")
        assert resp3.status_code == 200
        assert len(resp3.get_json()["network"]) == 1

    finally:
        _cleanup(app, tmp.name)


def test_agent_interactions_happy_path():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    try:
        app = _build_app(tmp.name)
        client = app.test_client()
        with app.app_context():
            db = bs.get_db()
            _seed_social_graph(db)

        resp = client.get("/api/agents/alice/interactions")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["agent_name"] == "alice"
        assert "incoming" in data and "outgoing" in data
        assert data["incoming_count"] == len(data["incoming"])
        assert data["outgoing_count"] == len(data["outgoing"])
        assert data["incoming_count"] == 3  # bob,charlie,diana follow alice
        assert data["outgoing_count"] == 2  # alice follows bob,charlie

    finally:
        _cleanup(app, tmp.name)


def test_agent_interactions_404_nonexistent():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    try:
        app = _build_app(tmp.name)
        client = app.test_client()
        with app.app_context():
            db = bs.get_db()
            _seed_social_graph(db)

        resp = client.get("/api/agents/ghost/interactions")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    finally:
        _cleanup(app, tmp.name)


def test_agent_interactions_limit_param_applies():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    try:
        app = _build_app(tmp.name)
        client = app.test_client()
        with app.app_context():
            db = bs.get_db()
            _seed_social_graph(db)

        resp = client.get("/api/agents/alice/interactions?limit=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["incoming"]) == 1
        assert len(data["outgoing"]) == 1

    finally:
        _cleanup(app, tmp.name)
