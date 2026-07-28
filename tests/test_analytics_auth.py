# SPDX-License-Identifier: MIT
"""Access control tests for the creator analytics blueprint.

Every ``/analytics/api/*`` route used to take its identity straight from a
caller-supplied ``X-Agent-ID`` header or ``?agent_id=`` param. Neither is a
credential, so ``GET /analytics/api/summary?agent_id=N`` returned any agent's
earnings, view counts and CSV export to anyone who asked.

The ``login_required`` decorator did not help. It only checked that the header
or param was *present*, never that it identified the caller, and it was applied
to zero routes. Its session fallback looked for ``session['agent_id']``, a key
the application never sets, so even the session path could not have worked.

These tests pin down the replacement: identity comes from a validated API key
or a logged in session, and a caller-supplied ``agent_id`` is honoured only
when it is the caller's own.
"""

import sqlite3

import pytest
from flask import Flask


ALL_API_ROUTES = [
    "/analytics/api/views",
    "/analytics/api/engagement",
    "/analytics/api/top-videos",
    "/analytics/api/audience",
    "/analytics/api/export/csv",
    "/analytics/api/summary",
]


@pytest.fixture()
def app(monkeypatch):
    import analytics_blueprint

    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            agent_name TEXT,
            api_key TEXT UNIQUE
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY, video_id TEXT, agent_id INTEGER,
            title TEXT, created_at REAL
        );
        CREATE TABLE views (
            id INTEGER PRIMARY KEY, video_id TEXT, agent_id INTEGER,
            ip_address TEXT, created_at REAL
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY, video_id TEXT, created_at REAL
        );
        CREATE TABLE votes (
            id INTEGER PRIMARY KEY, video_id TEXT, vote INTEGER, created_at REAL
        );
        CREATE TABLE earnings (
            id INTEGER PRIMARY KEY, agent_id INTEGER, video_id TEXT,
            amount REAL, reason TEXT, created_at REAL
        );
        CREATE TABLE subscriptions (
            id INTEGER PRIMARY KEY, following_id INTEGER
        );

        INSERT INTO agents (id, agent_name, api_key)
            VALUES (1, 'alice', 'bottube_sk_alice'), (2, 'bob', 'bottube_sk_bob');
        INSERT INTO videos VALUES (1, 'vid_alice', 1, 'Alice clip', 1700000000);
        INSERT INTO videos VALUES (2, 'vid_bob', 2, 'Bob clip', 1700000000);
        INSERT INTO earnings VALUES (1, 1, 'vid_alice', 12.5, 'tip_received', 1700000000);
        INSERT INTO earnings VALUES (2, 2, 'vid_bob', 999.0, 'tip_received', 1700000000);
        """
    )
    db.commit()

    monkeypatch.setattr(analytics_blueprint, "get_db", lambda: db)

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.secret_key = "analytics-auth-test"
    flask_app.register_blueprint(analytics_blueprint.analytics_bp)
    yield flask_app
    db.close()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.mark.parametrize("route", ALL_API_ROUTES)
def test_routes_reject_anonymous_callers(client, route):
    """No credentials at all must not return anyone's analytics."""
    assert client.get(route).status_code == 401


@pytest.mark.parametrize("route", ALL_API_ROUTES)
def test_routes_reject_a_bare_agent_id_param(client, route):
    """?agent_id= is a filter, not a credential. It must not authenticate."""
    assert client.get(f"{route}?agent_id=2").status_code == 401


@pytest.mark.parametrize("route", ALL_API_ROUTES)
def test_routes_reject_a_bare_agent_id_header(client, route):
    """X-Agent-ID is equally caller-supplied and equally not a credential."""
    assert client.get(route, headers={"X-Agent-ID": "2"}).status_code == 401


def test_unknown_api_key_is_rejected(client):
    """A key that is not in the agents table is not an identity."""
    resp = client.get("/analytics/api/summary", headers={"X-API-Key": "not-a-real-key"})
    assert resp.status_code == 401


def test_api_key_scopes_results_to_its_own_agent(client):
    """Alice's key returns Alice's numbers, without her naming an agent_id."""
    resp = client.get("/analytics/api/summary", headers={"X-API-Key": "bottube_sk_alice"})
    assert resp.status_code == 200
    assert resp.get_json()["total_earnings"] == 12.5


def test_api_key_cannot_read_another_agent(client):
    """The original leak: alice asking for bob's earnings."""
    resp = client.get(
        "/analytics/api/summary?agent_id=2", headers={"X-API-Key": "bottube_sk_alice"}
    )
    assert resp.status_code == 403


def test_api_key_may_name_its_own_agent_id(client):
    """Existing clients that pass their own agent_id keep working."""
    resp = client.get(
        "/analytics/api/summary?agent_id=1", headers={"X-API-Key": "bottube_sk_alice"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["total_earnings"] == 12.5


def test_web_session_authenticates_via_user_id(client):
    """Web login stores session['user_id'], not session['agent_id']."""
    with client.session_transaction() as sess:
        sess["user_id"] = 2
    resp = client.get("/analytics/api/summary")
    assert resp.status_code == 200
    assert resp.get_json()["total_earnings"] == 999.0


def test_web_session_cannot_read_another_agent(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
    resp = client.get("/analytics/api/summary?agent_id=2")
    assert resp.status_code == 403


def test_login_required_decorator_actually_blocks(app, client):
    """The decorator existed but could not fail. Prove it can now."""
    import analytics_blueprint

    @app.route("/guarded")
    @analytics_blueprint.login_required
    def guarded():
        return {"ok": True}

    assert client.get("/guarded").status_code == 401
    assert client.get("/guarded?agent_id=2").status_code == 401
    assert client.get("/guarded", headers={"X-API-Key": "bottube_sk_alice"}).status_code == 200
