# SPDX-License-Identifier: MIT
"""Both admin gates must resolve the same secret (fixes #1729)."""

import importlib
import sys

import pytest


@pytest.fixture()
def server_module(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTTUBE_AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(tmp_path / "bottube.db"))
    monkeypatch.delenv("BOTTUBE_ADMIN_KEY", raising=False)
    monkeypatch.delenv("RC_ADMIN_KEY", raising=False)
    sys.modules.pop("bottube_server", None)
    module = importlib.import_module("bottube_server")
    yield module
    sys.modules.pop("bottube_server", None)


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"BOTTUBE_ADMIN_KEY": "primary"}, "primary"),
        ({"RC_ADMIN_KEY": "alias"}, "alias"),
        ({"BOTTUBE_ADMIN_KEY": "primary", "RC_ADMIN_KEY": "alias"}, "primary"),
        ({}, ""),
    ],
    ids=["primary-only", "alias-only", "both-primary-wins", "neither"],
)
def test_admin_key_resolution(server_module, monkeypatch, env, expected):
    monkeypatch.delenv("BOTTUBE_ADMIN_KEY", raising=False)
    monkeypatch.delenv("RC_ADMIN_KEY", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert server_module._admin_key_from_env() == expected


def test_rc_admin_key_opens_trust_safety_gate(server_module, monkeypatch, tmp_path):
    monkeypatch.setenv("BOTTUBE_AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(tmp_path / "bottube.db"))
    monkeypatch.delenv("BOTTUBE_ADMIN_KEY", raising=False)
    monkeypatch.setenv("RC_ADMIN_KEY", "alias-secret")
    sys.modules.pop("bottube_server", None)
    module = importlib.import_module("bottube_server")
    client = module.app.test_client()
    ok = client.post("/admin/blocklist/add", headers={"X-Admin-Key": "alias-secret"}, json={})
    bad = client.post("/admin/blocklist/add", headers={"X-Admin-Key": "nope"}, json={})
    assert ok.status_code != 401
    assert bad.status_code in (401, 403)
    sys.modules.pop("bottube_server", None)


def test_rc_admin_key_opens_require_admin_gate(server_module, monkeypatch, tmp_path):
    monkeypatch.setenv("BOTTUBE_AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(tmp_path / "bottube.db"))
    monkeypatch.delenv("BOTTUBE_ADMIN_KEY", raising=False)
    monkeypatch.setenv("RC_ADMIN_KEY", "alias-secret")
    sys.modules.pop("bottube_server", None)
    module = importlib.import_module("bottube_server")
    client = module.app.test_client()
    ok = client.get("/api/admin/visitors", headers={"X-Admin-Key": "alias-secret"})
    bad = client.get("/api/admin/visitors", headers={"X-Admin-Key": "nope"})
    assert ok.status_code != 401
    assert bad.status_code in (401, 403)
    sys.modules.pop("bottube_server", None)
