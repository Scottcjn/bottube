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
    """Verify the trust-safety gate accepts the server-generated ephemeral key.

    When neither BOTTUBE_ADMIN_KEY nor RC_ADMIN_KEY is set in the
    environment, bottube_server generates a random ephemeral admin key
    on import. The trust-safety admin routes (/admin/blocklist/add)
    must accept that key via the X-Admin-Key header so that even an
    operator who forgot to set the env var can still hit the admin
    surface using the key logged at startup.
    """
    client = server_module.app.test_client()
    response = client.post('/admin/blocklist/add', headers={'X-Admin-Key': server_module.ADMIN_KEY}, json={})
    assert response.status_code != 401


def test_trust_safety_gate_accepts_bottube_admin_key(monkeypatch, tmp_path):
    """Verify the trust-safety gate accepts BOTTUBE_ADMIN_KEY and rejects others.

    When BOTTUBE_ADMIN_KEY is set in the environment, the server must
    use that exact value as the admin key. The matching request succeeds
    (not 401) while a request with a wrong value is rejected with 401.
    This guards against the server silently falling back to the
    ephemeral key when an env var is set.
    """
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
    """Verify the trust-safety gate does NOT accept RC_ADMIN_KEY alone.

    Security regression: RC_ADMIN_KEY is a legacy alias kept for backward
    compatibility but it must NOT grant access to the BOTTUBE admin
    surface. This test confirms that an env with only RC_ADMIN_KEY set
    rejects requests using that key with a 401. Without this guard an
    operator who migrated from RC could leave the legacy key enabled
    in CI and unintentionally grant BOTTUBE admin access.
    """
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
