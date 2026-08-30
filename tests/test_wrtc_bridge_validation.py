# SPDX-License-Identifier: MIT
"""Validation tests for Solana wRTC bridge request parsing."""

import sqlite3
from importlib import metadata
from pathlib import Path

import pytest
import werkzeug
from flask import Flask, g


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Build the bridge app with an isolated test DB."""
    import wrtc_bridge_blueprint as bridge

    db_path = tmp_path / "wrtc_bridge.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            sol_address TEXT,
            rtc_balance REAL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO agents (agent_name, api_key, sol_address, rtc_balance)
        VALUES (?, ?, ?, ?)
        """,
        (
            "bridgeuser",
            "bottube_sk_bridgeuser",
            "11111111111111111111111111111111",
            1000.0,
        ),
    )
    conn.commit()
    conn.close()

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["DATABASE"] = str(db_path)
    flask_app.register_blueprint(bridge.wrtc_bp)

    def _test_get_db():
        """Per-test SQLite connection swapped in for the bridge's get_db."""
        if "test_db" in g:
            return g.test_db
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        g.test_db = db
        return db

    monkeypatch.setattr(bridge, "get_db", _test_get_db)

    yield flask_app


@pytest.fixture()
def client(app):
    """Flask test client for the bridge app."""
    return app.test_client()


def _auth_headers():
    """Auth headers for an authenticated test agent."""
    return {"X-API-Key": "bottube_sk_bridgeuser"}


def _withdraw(client, payload):
    """POST a withdrawal request with the given amount/address."""
    return client.post(
        "/api/wrtc-bridge/withdraw",
        json=payload,
        headers=_auth_headers(),
    )


def test_wrtc_deposit_rejects_non_object_json(client):
    """A non-object JSON deposit body is rejected with 400."""
    resp = client.post(
        "/api/wrtc-bridge/deposit",
        json=["not", "an", "object"],
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"


def test_wrtc_deposit_rejects_non_string_tx_signature(client, monkeypatch):
    """A non-string tx signature is rejected with 400."""
    import wrtc_bridge_blueprint as bridge

    monkeypatch.setattr(
        bridge,
        "verify_wrtc_transfer",
        lambda _tx_signature: pytest.fail("verification should not run"),
    )

    resp = client.post(
        "/api/wrtc-bridge/deposit",
        json={"tx_signature": ["abc"]},
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "tx_signature must be a string"


def test_wrtc_withdraw_rejects_non_object_json(client):
    """A non-object JSON withdrawal body is rejected with 400."""
    resp = _withdraw(client, [{"to_address": "11111111111111111111111111111111"}])

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON object required"


def test_wrtc_withdraw_rejects_non_string_to_address(client):
    """A non-string to-address is rejected with 400."""
    resp = _withdraw(
        client,
        {"to_address": ["11111111111111111111111111111111"], "amount": 10},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "to_address must be a string"


@pytest.mark.parametrize("amount", ["abc", "NaN", "Infinity", True])
def test_wrtc_withdraw_rejects_non_finite_amounts(client, amount):
    """NaN/inf withdrawal amounts are rejected with 400."""
    resp = _withdraw(
        client,
        {"to_address": "11111111111111111111111111111111", "amount": amount},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "amount must be a finite number"


@pytest.mark.parametrize("limit", ["not-a-number", "0", "-5", "1.5", "true"])
def test_wrtc_history_rejects_invalid_limit(client, limit):
    """A malformed history limit is rejected with 400."""
    resp = client.get(
        f"/api/wrtc-bridge/history?limit={limit}",
        headers=_auth_headers(),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "limit must be a positive integer"


def test_rejected_wrtc_withdrawal_does_not_queue_or_debit(client):
    """A rejected withdrawal neither queues a payout nor debits the balance (atomic fail-closed)."""
    resp = _withdraw(
        client,
        {"to_address": "11111111111111111111111111111111", "amount": "NaN"},
    )
    assert resp.status_code == 400

    import wrtc_bridge_blueprint as bridge

    with sqlite3.connect(client.application.config["DATABASE"]) as db:
        bridge.init_wrtc_tables(db)
        queued = db.execute("SELECT COUNT(*) FROM wrtc_withdrawals").fetchone()[0]
        balance = db.execute(
            "SELECT rtc_balance FROM agents WHERE api_key = ?",
            ("bottube_sk_bridgeuser",),
        ).fetchone()[0]

    assert queued == 0
    assert balance == 1000.0


@pytest.mark.parametrize(
    "path",
    [
        "/wrtc",
        "/wrtc/deposit",
        "/wrtc/withdraw",
        "/wrtc/history",
        "/premium/wrtc",
    ],
)
def test_wrtc_html_alias_routes_redirect_to_bridge_console(client, path):
    """Legacy HTML alias routes redirect to the bridge console."""
    resp = client.get(path)

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/bridge/wrtc")


# --- /bridge landing template context tests (regression for #1359) ---

import wrtc_bridge_blueprint as bridge_mod  # noqa: E402


def test_bridge_landing_passes_template_context_for_anonymous_user(monkeypatch):
    """Anonymous user: g.user absent -> all 4 template kwargs set to safe defaults."""
    from flask import Flask, g

    captured = {}

    def _fake_render(template_name, **kwargs):
        """Stub render_template that captures the template and context."""
        captured["template_name"] = template_name
        captured["kwargs"] = kwargs
        return "<html>fake</html>"

    monkeypatch.setattr(bridge_mod, "render_template", _fake_render)

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(bridge_mod.wrtc_bp)

    client = flask_app.test_client()
    resp = client.get("/bridge")
    assert resp.status_code == 200
    assert resp.data == b"<html>fake</html>"
    assert captured["template_name"] == "bridge.html"
    kw = captured["kwargs"]
    # 4 missing vars get safe defaults
    assert kw["user_balance"] == 0
    assert kw["user_sol_address"] == ""
    # swap_url and reserve_wallet reuse the existing module constants
    assert kw["swap_url"] == bridge_mod.WRTC_BUY_URL
    assert kw["reserve_wallet"] == bridge_mod.WRTC_RESERVE_WALLET
    # 3 existing vars still present (no regression)
    assert kw["wrtc_mint"] == bridge_mod.WRTC_MINT
    assert kw["wrtc_reserve_wallet"] == bridge_mod.WRTC_RESERVE_WALLET
    assert kw["wrtc_buy_url"] == bridge_mod.WRTC_BUY_URL


def test_bridge_landing_uses_authenticated_user_balance_and_sol_address(monkeypatch):
    """Authenticated user: g.user is set -> user_balance and user_sol_address flow through."""
    from flask import Flask, g

    captured = {}

    def _fake_render(template_name, **kwargs):
        """Stub render_template that captures the template and context."""
        captured["kwargs"] = kwargs
        return "<html>fake</html>"

    monkeypatch.setattr(bridge_mod, "render_template", _fake_render)

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(bridge_mod.wrtc_bp)

    @flask_app.before_request
    def _seed_user():
        """Seed an authenticated user row before the request runs."""
        g.user = {
            "id": 42,
            "agent_name": "alice",
            "sol_address": "SoLaNaAdDrEsS1111111111111111111111",
            "rtc_balance": 12.5,
        }

    client = flask_app.test_client()
    resp = client.get("/bridge")
    assert resp.status_code == 200
    kw = captured["kwargs"]
    assert kw["user_balance"] == 12.5
    assert kw["user_sol_address"] == "SoLaNaAdDrEsS1111111111111111111111"


def test_bridge_landing_handles_user_with_null_sol_address(monkeypatch):
    """Auth user with NULL sol_address -> empty string fallback (no 500)."""
    from flask import Flask, g

    captured = {}

    def _fake_render(template_name, **kwargs):
        """Stub render_template that captures the template and context."""
        captured["kwargs"] = kwargs
        return "<html>fake</html>"

    monkeypatch.setattr(bridge_mod, "render_template", _fake_render)

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(bridge_mod.wrtc_bp)

    @flask_app.before_request
    def _seed_user():
        """Seed an authenticated user row before the request runs."""
        g.user = {"id": 7, "agent_name": "bob", "sol_address": None, "rtc_balance": 0.0}

    client = flask_app.test_client()
    resp = client.get("/bridge")
    assert resp.status_code == 200
    kw = captured["kwargs"]
    assert kw["user_sol_address"] == ""
    assert kw["user_balance"] == 0.0
    assert kw["swap_url"] == bridge_mod.WRTC_BUY_URL
    assert kw["reserve_wallet"] == bridge_mod.WRTC_RESERVE_WALLET
