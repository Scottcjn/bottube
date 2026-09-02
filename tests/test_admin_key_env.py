import importlib
import sqlite3
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


def test_trust_safety_gate_rejects_rc_only_key(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTTUBE_AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(tmp_path / "bottube.db"))
    monkeypatch.delenv("BOTTUBE_ADMIN_KEY", raising=False)
    monkeypatch.setenv("RC_ADMIN_KEY", "legacy-rc-key")
    sys.modules.pop("bottube_server", None)
    module = importlib.import_module("bottube_server")
    client = module.app.test_client()
    response = client.post('/admin/blocklist/add', headers={'X-Admin-Key': 'legacy-rc-key'}, json={})
    assert response.status_code == 401
    sys.modules.pop("bottube_server", None)


def test_trust_safety_schema_supports_fresh_db_then_retries_agent_migration(server_module):
    client = server_module.app.test_client()
    response = client.post(
        "/admin/blocklist/add",
        headers={"X-Admin-Key": server_module.ADMIN_KEY},
        json={"sha256": "a" * 64, "category": "malware"},
    )
    assert response.status_code == 200

    conn = sqlite3.connect(server_module.DB_PATH)
    try:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(agents)").fetchall()
        }
    finally:
        conn.close()

    assert {
        "tos_version_accepted",
        "tos_accepted_at",
        "tos_accepted_ip",
        "is_suspended",
        "suspended_reason",
        "suspended_at",
    } <= columns
