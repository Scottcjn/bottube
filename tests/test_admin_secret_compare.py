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
