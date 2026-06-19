# Regression tests for GET /api/dashboard/analytics days param validation.
#
# Before the fix the endpoint silently coerced non-integer / out-of-range
# values to the default (30) instead of telling the client something was wrong.
# Now it returns a clean 400 JSON error.
import datetime as _dt
import time

# Compatibility: some Python builds removed utcfromtimestamp (deprecated in 3.12).
# The production server runs standard CPython where it still works.
if not hasattr(_dt, "utcfromtimestamp"):
    class _ShimDT:
        def __init__(self, ts):
            self._ts = ts
        def strftime(self, fmt):
            return time.strftime(fmt, time.gmtime(self._ts))
    _dt.utcfromtimestamp = lambda ts: _ShimDT(ts)


def _setup_agent(app):
    """Insert a test agent and return its id."""
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """INSERT INTO agents
               (agent_name, display_name, api_key, password_hash, bio,
                avatar_url, created_at, last_active)
               VALUES (?, ?, ?, '', '', '', ?, ?)""",
            ("dashdaysbot", "Dash Days Bot", "sk_dashdays_test",
             time.time(), time.time()),
        )
        db.commit()
        return int(cur.lastrowid)


def _login(client, agent_id):
    with client.session_transaction() as sess:
        sess["user_id"] = agent_id


def test_days_default_when_omitted(app, client):
    agent_id = _setup_agent(app)
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["labels"]) == 30


def test_days_non_integer_returns_400(app, client):
    agent_id = _setup_agent(app)
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=abc")
    assert resp.status_code == 400
    assert "integer" in resp.get_json()["error"]


def test_days_below_minimum_returns_400(app, client):
    agent_id = _setup_agent(app)
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=6")
    assert resp.status_code == 400
    assert "7" in resp.get_json()["error"]


def test_days_above_maximum_returns_400(app, client):
    agent_id = _setup_agent(app)
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=91")
    assert resp.status_code == 400
    assert "90" in resp.get_json()["error"]


def test_days_at_lower_boundary(app, client):
    agent_id = _setup_agent(app)
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=7")
    assert resp.status_code == 200
    assert len(resp.get_json()["labels"]) == 7


def test_days_at_upper_boundary(app, client):
    agent_id = _setup_agent(app)
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=90")
    assert resp.status_code == 200
    assert len(resp.get_json()["labels"]) == 90


def test_days_zero_returns_400(app, client):
    agent_id = _setup_agent(app)
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=0")
    assert resp.status_code == 400


def test_days_negative_returns_400(app, client):
    agent_id = _setup_agent(app)
    _login(client, agent_id)
    resp = client.get("/api/dashboard/analytics?days=-5")
    assert resp.status_code == 400
