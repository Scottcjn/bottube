# SPDX-License-Identifier: MIT
"""Regression tests: the USDC blueprint must query the real column names.

Two queries referenced columns that do not exist in production
(see the schema in ``bottube_server.py``):

* ``SELECT name FROM agents`` — the identity column is ``agent_name``.
  ``get_authenticated_agent()`` is the front door for /deposit, /balance,
  /tip, /premium and /payout, so every authenticated USDC call raised
  ``sqlite3.OperationalError: no such column: name`` -> HTTP 500.
* ``SELECT agent FROM videos WHERE id = ?`` — ``videos`` has ``agent_id``
  (int FK) and ``video_id`` (the public string); ``id`` is the integer PK,
  so tipping by ``video_id`` could never resolve a creator.

The fixture below uses the production schema on purpose: the pre-existing
USDC fixture declared ``agents(name TEXT PRIMARY KEY)``, which is why the
suite agreed with the broken queries.
"""

import sqlite3
import time
from importlib import metadata

import pytest
import werkzeug
from flask import Flask, g

import usdc_blueprint

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


@pytest.fixture
def usdc_client(tmp_path):
    db_path = tmp_path / "bottube.db"
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(usdc_blueprint.usdc_bp)

    @app.before_request
    def _open_db():
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row

    @app.teardown_request
    def _close_db(_exc):
        db = getattr(g, "db", None)
        if db is not None:
            db.close()

    now = time.time()
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT UNIQUE NOT NULL,
                api_key TEXT UNIQUE NOT NULL,
                eth_address TEXT DEFAULT ''
            );
            CREATE TABLE videos (
                id INTEGER PRIMARY KEY,
                video_id TEXT UNIQUE NOT NULL,
                agent_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        usdc_blueprint.init_usdc_tables(db)
        db.executemany(
            "INSERT INTO agents (agent_name, api_key) VALUES (?, ?)",
            [("alice", "key-alice"), ("bob", "key-bob")],
        )
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, created_at) "
            "VALUES (?, (SELECT id FROM agents WHERE agent_name = 'bob'), ?, ?)",
            ("vid_bob_1", "Bob's clip", now),
        )
        db.execute(
            """
            INSERT INTO usdc_balances
            (agent_name, balance_usdc, total_deposited, total_spent, total_earned, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("alice", 10.0, 10.0, 0.0, 0.0, now),
        )
        db.commit()

    client = app.test_client()
    client.db_path = db_path
    return client


def _balance(db_path, agent_name):
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        return db.execute(
            "SELECT balance_usdc, total_spent, total_earned FROM usdc_balances "
            "WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()


def test_balance_endpoint_authenticates_against_agent_name(usdc_client):
    """Smoke test for get_authenticated_agent(): used to be a hard 500."""
    response = usdc_client.get(
        "/api/usdc/balance", headers={"X-API-Key": "key-alice"}
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["agent"] == "alice"
    assert body["balance_usdc"] == pytest.approx(10.0)


def test_unknown_api_key_is_401_not_500(usdc_client):
    response = usdc_client.get(
        "/api/usdc/balance", headers={"X-API-Key": "key-nobody"}
    )

    assert response.status_code == 401


def test_tip_resolves_creator_from_public_video_id(usdc_client):
    response = usdc_client.post(
        "/api/usdc/tip",
        json={"video_id": "vid_bob_1", "amount_usdc": 1.0},
        headers={"X-API-Key": "key-alice"},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["tip"]["to"] == "bob"
    assert body["tip"]["video_id"] == "vid_bob_1"

    alice = _balance(usdc_client.db_path, "alice")
    bob = _balance(usdc_client.db_path, "bob")
    assert alice["balance_usdc"] == pytest.approx(9.0)
    assert alice["total_spent"] == pytest.approx(1.0)
    assert bob["total_earned"] > 0


def test_tip_for_unknown_video_id_is_404_not_500(usdc_client):
    response = usdc_client.post(
        "/api/usdc/tip",
        json={"video_id": "vid_missing", "amount_usdc": 1.0},
        headers={"X-API-Key": "key-alice"},
    )

    assert response.status_code == 404
    assert _balance(usdc_client.db_path, "alice")["balance_usdc"] == pytest.approx(10.0)
