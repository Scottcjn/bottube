# SPDX-License-Identifier: MIT
"""Validation tests for Ergo bridge request parsing."""

import sqlite3

import pytest
import werkzeug
from flask import Flask, g

import ergo_bridge_blueprint


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "test"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Build an isolated Flask app around just the Ergo bridge blueprint.

    Registers only `ergo_bp` on a throwaway `Flask(__name__)` with a
    hand-built minimal schema (agents + earnings) rather than the full
    `bottube_server` app, so these tests exercise request validation in
    isolation without needing the rest of the platform wired up.
    """
    db_path = tmp_path / "ergo_bridge.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            rtc_balance REAL DEFAULT 0
        );
        CREATE TABLE earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            amount REAL,
            reason TEXT,
            created_at REAL
        );
        INSERT INTO agents (agent_name, api_key, rtc_balance)
        VALUES ('ergo_agent', 'bottube_sk_ergo_agent', 100.0);
        """
    )
    ergo_bridge_blueprint.init_ergo_tables(conn)
    conn.commit()
    conn.close()

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.register_blueprint(ergo_bridge_blueprint.ergo_bp)

    def _test_get_db():
        """Replace `ergo_bridge_blueprint.get_db` with a per-request connection to the test DB.

        Swapped in via `monkeypatch.setattr` below so every request the
        blueprint handles stays confined to `db_path`, instead of whatever
        database the blueprint module would otherwise resolve.
        """
        if "test_db" in g:
            return g.test_db
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        g.test_db = db
        return db

    @app.teardown_appcontext
    def _close_db(_exc):
        """Close the per-request test connection so SQLite file handles don't leak across requests."""
        db = g.pop("test_db", None)
        if db is not None:
            db.close()

    monkeypatch.setattr(ergo_bridge_blueprint, "get_db", _test_get_db)
    monkeypatch.setattr(ergo_bridge_blueprint, "ADMIN_KEY", "test-admin")

    test_client = app.test_client()
    test_client.db_path = db_path
    return test_client


def _auth_headers():
    """Return the API key header for the single agent seeded by the `client` fixture."""
    return {"X-API-Key": "bottube_sk_ergo_agent"}


def _admin_headers():
    """Return the admin key header, matching the fixture's patched `ADMIN_KEY`."""
    return {"X-Admin-Key": "test-admin"}


def _counts_and_balance(db_path):
    """Snapshot deposit/withdrawal row counts and the agent's RTC balance.

    Every rejection test below compares this snapshot before and after a
    malformed request, so a validator that rejects the HTTP response but
    still mutates the ledger (creates a deposit/withdrawal row or moves
    the balance) gets caught here rather than looking like a clean 400.
    """
    with sqlite3.connect(str(db_path)) as db:
        return {
            "deposits": db.execute("SELECT COUNT(*) FROM ergo_deposits").fetchone()[0],
            "withdrawals": db.execute(
                "SELECT COUNT(*) FROM ergo_withdrawals"
            ).fetchone()[0],
            "balance": db.execute(
                "SELECT rtc_balance FROM agents WHERE api_key = ?",
                ("bottube_sk_ergo_agent",),
            ).fetchone()[0],
        }


def test_ergo_deposit_rejects_non_object_json(client):
    """A JSON array body to /deposit must 400 without creating a deposit row or touching balance."""
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/deposit",
        json=["not", "an", "object"],
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"
    assert _counts_and_balance(client.db_path) == before


def test_ergo_deposit_rejects_non_string_tx_id(client):
    """A list-typed `tx_id` must be rejected before it can reach chain-lookup code expecting a string."""
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/deposit",
        json={"tx_id": ["abc"]},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "tx_id must be a string"
    assert _counts_and_balance(client.db_path) == before


def test_ergo_withdraw_rejects_non_object_json(client):
    """A JSON array body to /withdraw must 400 without creating a withdrawal row or debiting balance.

    The payload is a list *containing* an otherwise-valid withdrawal
    object, to prove the top-level shape check runs before anything
    inspects the contents.
    """
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/withdraw",
        json=[{"amount_rtc": 10, "address": "9abc"}],
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"
    assert _counts_and_balance(client.db_path) == before


def test_ergo_withdraw_rejects_non_string_address(client):
    """A list-typed `address` must be rejected, not passed through to on-chain send logic as-is."""
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/withdraw",
        json={"amount_rtc": 10, "address": ["9abc"]},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "address must be a string"
    assert _counts_and_balance(client.db_path) == before


@pytest.mark.parametrize("amount", ["abc", "NaN", "Infinity", True, 0, -1])
def test_ergo_withdraw_rejects_invalid_amount_without_queue_or_debit(client, amount):
    """Non-numeric, NaN, Infinity, boolean, zero, and negative amounts must all be rejected identically.

    `True` is included deliberately: Python's `bool` is a subclass of
    `int`, so a naive `isinstance(amount, (int, float))` check would let
    `True`/`False` slip through as `1`/`0` unless the validator excludes
    bools explicitly.
    """
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/withdraw",
        json={"amount_rtc": amount, "address": "9abc"},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "amount_rtc must be a finite positive number"
    assert _counts_and_balance(client.db_path) == before


@pytest.mark.parametrize("limit", ["abc", "-5", "0"])
def test_ergo_history_rejects_invalid_limit(client, limit):
    """Non-numeric, negative, and zero `limit` values must all 400 with the same message.

    Calls `ergo_history()` directly inside a manually pushed request
    context rather than through `client.get`, since the view here returns
    a `(response, status)` tuple rather than relying on Flask's default
    status-code handling.
    """
    app = client.application

    with app.test_request_context(
        f"/api/ergo/history?limit={limit}",
        headers=_auth_headers(),
    ):
        resp, status = ergo_bridge_blueprint.ergo_history()

    assert status == 400
    assert resp.get_json()["error"] == "limit must be a positive integer"


def test_ergo_history_clamps_large_limit(client):
    """A `limit` far above any sane page size must still succeed by clamping, not by 400ing or over-fetching.

    `limit=500` against an agent with zero deposits/withdrawals confirms
    the endpoint clamps to its internal max and returns normally rather
    than treating an oversized limit as an error the way `_parse_limit`
    elsewhere in the codebase does -- these are two independently
    validated endpoints with different limit-handling policies.
    """
    app = client.application

    with app.test_request_context(
        "/api/ergo/history?limit=500",
        headers=_auth_headers(),
    ):
        resp = ergo_bridge_blueprint.ergo_history()

    assert resp.status_code == 200
    assert resp.get_json() == {"deposits": [], "withdrawals": []}


def test_process_withdrawals_rejects_non_object_json(client):
    """The admin process-withdrawals endpoint must 400 on a non-object body without touching the ledger.

    Uses admin auth (not the agent's API key) since this is the
    maintainer-facing endpoint that actually marks a withdrawal as sent
    on-chain -- its input validation matters at least as much as the
    user-facing deposit/withdraw endpoints.
    """
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/process-withdrawals",
        json=["withdrawal_id", "tx_id"],
        headers=_admin_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"
    assert _counts_and_balance(client.db_path) == before


def test_process_withdrawals_rejects_non_string_tx_id(client):
    """A list-typed `tx_id` on the admin confirm-withdrawal call must be rejected, not stored as the on-chain reference."""
    before = _counts_and_balance(client.db_path)

    resp = client.post(
        "/api/ergo/process-withdrawals",
        json={"withdrawal_id": 1, "tx_id": ["ergo_tx"]},
        headers=_admin_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "tx_id must be a string"
    assert _counts_and_balance(client.db_path) == before
