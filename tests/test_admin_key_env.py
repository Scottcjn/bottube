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


def test_trust_safety_gate_uses_ephemeral_admin_key(server_module):
    client = server_module.app.test_client()
    response = client.post('/admin/blocklist/add', headers={'X-Admin-Key': server_module.ADMIN_KEY}, json={})
    assert response.status_code != 401


def test_trust_safety_gate_accepts_bottube_admin_key(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTTUBE_AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(tmp_path / "bottube.db"))
    monkeypatch.setenv("BOTTUBE_ADMIN_KEY", "bot-key")
    monkeypatch.delenv("RC_ADMIN_KEY", raising=False)
    sys.modules.pop("bottube_server", None)
    module = importlib.import_module("bottube_server")
    client = module.app.test_client()
    ok = client.post('/admin/blocklist/add', headers={'X-Admin-Key': 'bot-key'}, json={})
    bad = client.post('/admin/blocklist/add', headers={'X-Admin-Key': 'wrong'}, json={})
    assert ok.status_code != 401
    assert bad.status_code == 401
    sys.modules.pop("bottube_server", None)


def test_trust_safety_gate_accepts_rc_admin_key_alias(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTTUBE_AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(tmp_path / "bottube.db"))
    monkeypatch.delenv("BOTTUBE_ADMIN_KEY", raising=False)
    monkeypatch.setenv("RC_ADMIN_KEY", "legacy-rc-key")
    sys.modules.pop("bottube_server", None)
    module = importlib.import_module("bottube_server")
    client = module.app.test_client()
    response = client.post('/admin/blocklist/add', headers={'X-Admin-Key': 'legacy-rc-key'}, json={})
    assert response.status_code != 401
    sys.modules.pop("bottube_server", None)
