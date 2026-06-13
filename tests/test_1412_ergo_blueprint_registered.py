"""Tests for Bottube #1412 — ergo_bp must be registered on the Flask app.

Before this fix, `ergo_bp` was defined in `ergo_bridge_blueprint.py` but
never registered on the Flask app in `bottube_server.py`. Calling any of
the 7 routes declared on the blueprint (e.g. `/api/ergo/info`) returned
HTTP 404.

After the fix, all 7 routes resolve correctly via Flask's URL map and
return the documented JSON shapes (or 400 on missing required fields).
"""

import pytest

# Import the server module exactly as production does (it runs at import time).
import bottube_server as server


@pytest.fixture
def ergo_client():
    """Reuse the server's Flask test_client. The server module is loaded
    once via `import bottube_server`, so registering blueprints happens at
    import time — if the import succeeds with our fix in place, all 7
    routes are live."""
    return server.app.test_client()


def test_ergo_bp_routes_are_registered():
    """All 7 routes from ergo_bp must appear in the Flask URL map."""
    rules = {rule.rule for rule in server.app.url_map.iter_rules()}
    expected_routes = {
        "/api/ergo/info",
        "/api/ergo/deposit",
        "/api/ergo/withdraw",
        "/api/ergo/history",
        "/api/ergo/rate",
        "/api/ergo/process-withdrawals",
        "/api/ergo/pending-withdrawals",
    }
    missing = expected_routes - rules
    assert not missing, (
        "ergo_bp routes missing from Flask URL map (Bottube #1412 regression): "
        f"{missing}"
    )


def test_ergo_info_returns_json(ergo_client):
    """/api/ergo/info must return JSON describing the bridge."""
    resp = ergo_client.get("/api/ergo/info")
    assert resp.status_code == 200, (
        f"expected 200, got {resp.status_code}: {resp.data[:300]!r}"
    )
    payload = resp.get_json()
    assert isinstance(payload, dict)
    # The public info payload should at least identify the bridge name and
    # mention ERG; exact keys depend on the implementation but these are
    # the universal ones for bridge_info endpoints.
    body = repr(payload).lower()
    assert "erg" in body


def test_ergo_rate_returns_json(ergo_client):
    """/api/ergo/rate must return a JSON rate payload (or 503 if explorer
    unreachable — accept either, but never 404)."""
    resp = ergo_client.get("/api/ergo/rate")
    assert resp.status_code != 404, (
        f"ergo_bp is still 404 on /api/ergo/rate — Bottube #1412 not fixed"
    )
    # 200 with JSON, or 503 (upstream Ergo explorer unreachable) are both
    # acceptable; only 404 indicates the blueprint is unregistered.
    assert resp.status_code in (200, 502, 503), (
        f"unexpected status {resp.status_code} from /api/ergo/rate"
    )


def test_ergo_history_returns_json_for_anonymous_client(ergo_client):
    """/api/ergo/history should return either an empty list (200) or an
    auth-required error (401/403). Anything else, especially 404, means
    the blueprint is still unregistered."""
    resp = ergo_client.get("/api/ergo/history")
    assert resp.status_code != 404, (
        f"ergo_bp is still 404 on /api/ergo/history — Bottube #1412 not fixed"
    )
    assert resp.status_code in (200, 400, 401, 403), (
        f"unexpected status {resp.status_code} from /api/ergo/history: "
        f"{resp.data[:200]!r}"
    )


def test_other_bridge_blueprints_still_registered():
    """Regression check: usdc_bp, wrtc_bp, base_wrtc_bp must still be in
    the URL map (the fix only adds ergo_bp; nothing else should change)."""
    rules = {rule.rule for rule in server.app.url_map.iter_rules()}
    for path in ("/api/usdc/info", "/api/wrtc-bridge/info", "/api/base-bridge/info"):
        assert path in rules, (
            f"existing bridge blueprint route {path} disappeared after "
            f"ergo_bp registration — regression in Bottube #1412 fix"
        )


def test_no_unprotected_admin_routes_exposed(ergo_client):
    """/api/ergo/process-withdrawals and /api/ergo/pending-withdrawals are
    admin-only. They must be present in the URL map (registered) but not
    callable without the admin key. 401/403 is the expected response."""
    rules = {rule.rule for rule in server.app.url_map.iter_rules()}
    assert "/api/ergo/process-withdrawals" in rules
    assert "/api/ergo/pending-withdrawals" in rules
    resp = ergo_client.post("/api/ergo/process-withdrawals")
    assert resp.status_code in (401, 403, 405), (
        f"admin endpoint callable without auth: status={resp.status_code}"
    )