# SPDX-License-Identifier: MIT

import sys
import os
import sqlite3
import importlib
import tempfile
from pathlib import Path


# ------------------------------------------------------------
# Patch sqlite ONLY during import to block prod DB path
# ------------------------------------------------------------

_original_connect = sqlite3.connect


def _safe_import_connect(path, *args, **kwargs):
    # Prevent hardcoded production DB access during import
    if isinstance(path, str) and "/root/bottube/" in path:
        return _original_connect(":memory:")
    return _original_connect(path, *args, **kwargs)


sqlite3.connect = _safe_import_connect

if "bottube_server" in sys.modules:
    del sys.modules["bottube_server"]

bs = importlib.import_module("bottube_server")

# Restore sqlite immediately (critical for test isolation)
sqlite3.connect = _original_connect


# ------------------------------------------------------------
# App builder
# ------------------------------------------------------------

def _build_app(db_path):
    bs.DB_PATH = Path(db_path)
    bs.app.config["TESTING"] = True

    with bs.app.app_context():
        bs.init_db()

    return bs.app


def _create_agent(db, name, balance=0):
    api_key = f"test_key_{name}"
    db.execute(
        """
        INSERT INTO agents
        (agent_name, display_name, api_key, rtc_balance, created_at)
        VALUES (?, ?, ?, ?, strftime('%s','now'))
        """,
        (name, name, api_key, balance),
    )
    db.commit()
    return api_key


def _cleanup(app, db_path):
    # Close DB to prevent Windows file lock
    with app.app_context():
        try:
            db = bs.get_db()
            db.close()
        except Exception:
            pass

    if os.path.exists(db_path):
        os.unlink(db_path)


# ------------------------------------------------------------
# Auth Required
# ------------------------------------------------------------

def test_tip_requires_auth():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()

    try:
        app = _build_app(tmp.name)
        client = app.test_client()

        resp = client.post(
            "/api/agents/alice/tip",
            json={"amount": 1},
        )

        assert resp.status_code == 401
        assert b"missing x-api-key" in resp.data.lower()

    finally:
        _cleanup(app, tmp.name)


# ------------------------------------------------------------
# Invalid API Key
# ------------------------------------------------------------

def test_invalid_api_key():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()

    try:
        app = _build_app(tmp.name)
        client = app.test_client()

        resp = client.post(
            "/api/agents/alice/tip",
            json={"amount": 1},
            headers={"X-API-Key": "bad_key"},
        )

        assert resp.status_code == 401
        assert b"invalid api key" in resp.data.lower()

    finally:
        _cleanup(app, tmp.name)


# ------------------------------------------------------------
# Self-Tipping Blocked
# ------------------------------------------------------------

def test_self_tipping_blocked():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()

    try:
        app = _build_app(tmp.name)
        client = app.test_client()

        with app.app_context():
            db = bs.get_db()
            key = _create_agent(db, "alice", balance=10)

        resp = client.post(
            "/api/agents/alice/tip",
            json={"amount": 1},
            headers={"X-API-Key": key},
        )

        assert resp.status_code == 400
        assert b"cannot tip yourself" in resp.data.lower()

    finally:
        _cleanup(app, tmp.name)


# ------------------------------------------------------------
# Creator Not Found
# ------------------------------------------------------------

def test_creator_not_found():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()

    try:
        app = _build_app(tmp.name)
        client = app.test_client()

        with app.app_context():
            db = bs.get_db()
            sender_key = _create_agent(db, "alice", balance=10)

        resp = client.post(
            "/api/agents/ghost/tip",
            json={"amount": 1},
            headers={"X-API-Key": sender_key},
        )

        assert resp.status_code == 404
        assert b"creator not found" in resp.data.lower()

    finally:
        _cleanup(app, tmp.name)


# ------------------------------------------------------------
# Insufficient Balance
# ------------------------------------------------------------

def test_insufficient_balance():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()

    try:
        app = _build_app(tmp.name)
        client = app.test_client()

        with app.app_context():
            db = bs.get_db()
            sender_key = _create_agent(db, "alice", balance=0)
            _create_agent(db, "bob", balance=0)

        resp = client.post(
            "/api/agents/bob/tip",
            json={"amount": 5},
            headers={"X-API-Key": sender_key},
        )

        assert resp.status_code == 400
        assert b"insufficient rtc balance" in resp.data.lower()

    finally:
        _cleanup(app, tmp.name)


# ------------------------------------------------------------
# Successful Tip
# ------------------------------------------------------------

def test_successful_tip_creates_record_and_updates_balance():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()

    try:
        app = _build_app(tmp.name)
        client = app.test_client()

        with app.app_context():
            db = bs.get_db()
            sender_key = _create_agent(db, "alice", balance=10)
            _create_agent(db, "bob", balance=0)

        resp = client.post(
            "/api/agents/bob/tip",
            json={"amount": 2, "message": "nice work"},
            headers={"X-API-Key": sender_key},
        )

        assert resp.status_code == 200
        data = resp.get_json()

        assert data["ok"] is True
        assert data["amount"] == 2
        assert data["to"] == "bob"
        assert data["message"] == "nice work"

        with app.app_context():
            db = bs.get_db()
            sender = db.execute(
                "SELECT rtc_balance FROM agents WHERE agent_name='alice'"
            ).fetchone()
            recipient = db.execute(
                "SELECT rtc_balance FROM agents WHERE agent_name='bob'"
            ).fetchone()

            assert sender["rtc_balance"] == 8
            assert recipient["rtc_balance"] == 2

    finally:
        _cleanup(app, tmp.name)