# SPDX-License-Identifier: MIT
"""Admin-key and CSRF checks must be constant-time and must not 500 on junk input.

hmac.compare_digest raises TypeError for str arguments containing non-ASCII
characters (and for non-str arguments), so a junk X-Admin-Key header or a
non-string JSON csrf_token used to surface as an HTTP 500 instead of a
401/403. Several admin gates also used plain ``!=`` (not constant-time).
"""
import hmac
import importlib
import sys

import pytest

ADMIN = "k-admin-secret"
JUNK = "\xfcber-key"  # latin-1 encodable header value, non-ASCII


@pytest.fixture()
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTTUBE_AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(tmp_path / "bottube.db"))
    monkeypatch.setenv("BOTTUBE_ADMIN_KEY", ADMIN)
    monkeypatch.delenv("RC_ADMIN_KEY", raising=False)
    sys.modules.pop("bottube_server", None)
    module = importlib.import_module("bottube_server")
    module.init_db()
    module.app.config["TESTING"] = True
    yield module
    sys.modules.pop("bottube_server", None)


@pytest.mark.parametrize("path,method", [
    ("/admin/blocklist/add", "post"),          # _ts_admin_ok
    ("/api/admin/visitors", "get"),            # _require_admin
    ("/api/admin/reports", "get"),             # inline gate
    ("/api/admin/reports/1/resolve", "post"),  # inline gate
    ("/api/admin/scrapers", "get"),            # scraper_detective gate
])
def test_non_ascii_admin_key_is_rejected_not_500(server, path, method):
    client = server.app.test_client()
    resp = getattr(client, method)(path, headers={"X-Admin-Key": JUNK}, json={})
    assert resp.status_code in (401, 403), resp.status_code


@pytest.mark.parametrize("path,method,ok_status", [
    ("/api/admin/visitors", "get", 200),
    ("/api/admin/reports", "get", 200),
    ("/api/admin/scrapers", "get", 200),
    ("/api/store/stats", "get", 200),
])
def test_admin_gates_compare_in_constant_time(server, monkeypatch, path, method, ok_status):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    client = server.app.test_client()
    resp = getattr(client, method)(path, headers={"X-Admin-Key": ADMIN})
    assert resp.status_code == ok_status
    assert calls, f"{path} compared the admin key without hmac.compare_digest"


def test_non_string_json_csrf_token_is_403_not_500(server):
    client = server.app.test_client()
    with client.session_transaction() as sess:
        sess["csrf_token"] = "a" * 64
    resp = client.post("/login", json={"csrf_token": 12345})
    assert resp.status_code == 403


def test_non_ascii_csrf_header_is_403_not_500(server):
    client = server.app.test_client()
    with client.session_transaction() as sess:
        sess["csrf_token"] = "a" * 64
    resp = client.post("/login", headers={"X-CSRF-Token": JUNK}, json={})
    assert resp.status_code == 403


def test_lone_surrogate_json_csrf_token_is_403_not_500(server):
    # A JSON string may carry an unpaired surrogate, which UTF-8 cannot encode.
    client = server.app.test_client()
    with client.session_transaction() as sess:
        sess["csrf_token"] = "a" * 64
    resp = client.post(
        "/login",
        data='{"csrf_token": "\\ud800"}',
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("value", ["", None, 12345, JUNK, "\ud800", ADMIN + "x"])
def test_secret_equals_rejects_junk_without_raising(server, value):
    assert server._secret_equals(value, ADMIN) is False


def test_secret_equals_accepts_exact_match(server):
    assert server._secret_equals(ADMIN, ADMIN) is True
    assert server._secret_equals(ADMIN, "") is False


def test_syndication_admin_gate_rejects_junk_without_500(server, monkeypatch):
    import syndication_routes

    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    for key, expected in [(JUNK, False), ("", False), (ADMIN, True)]:
        headers = {"X-Admin-Key": key} if key else {}
        with server.app.test_request_context("/", headers=headers):
            assert syndication_routes._is_admin_request() is expected
    assert calls, "syndication admin gate compared the key without hmac.compare_digest"


# ---------------------------------------------------------------------------
# Bridge blueprints (banano / ergo / base wRTC) and legacy wrtc_bridge.py
# ---------------------------------------------------------------------------

BRIDGE_MODULES = ["banano_blueprint", "ergo_bridge_blueprint", "base_wrtc_bridge_blueprint"]


def _import_or_skip(name):
    try:
        return importlib.import_module(name)
    except Exception as exc:  # pragma: no cover - env-dependent optional deps
        pytest.skip(f"{name} not importable in this env: {exc}")


@pytest.mark.parametrize("name", BRIDGE_MODULES)
def test_bridge_admin_ok_rejects_junk_without_raising(name, monkeypatch):
    mod = _import_or_skip(name)
    monkeypatch.setattr(mod, "ADMIN_KEY", ADMIN)
    for value in (JUNK, "\ud800", "", None, 12345, ADMIN + "x"):
        assert mod._admin_ok(value) is False, value
    assert mod._admin_ok(ADMIN) is True


@pytest.mark.parametrize("name", BRIDGE_MODULES)
def test_bridge_admin_ok_uses_constant_time_compare(name, monkeypatch):
    mod = _import_or_skip(name)
    monkeypatch.setattr(mod, "ADMIN_KEY", ADMIN)
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    assert mod._admin_ok(ADMIN) is True
    assert calls


def test_wrtc_bridge_is_admin_constant_time_and_no_raise(monkeypatch):
    import flask

    mod = _import_or_skip("wrtc_bridge")
    monkeypatch.setattr(mod, "ADMIN_KEY", ADMIN)
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    app = flask.Flask(__name__)
    for key, expected in [(JUNK, False), ("", False), (ADMIN, True)]:
        headers = {"X-Admin-Key": key} if key else {}
        with app.test_request_context("/", headers=headers):
            assert bool(mod._is_admin()) is expected
    assert calls

    monkeypatch.setattr(mod, "ADMIN_KEY", "")
    with app.test_request_context("/", headers={"X-Admin-Key": "anything"}):
        assert not mod._is_admin()
