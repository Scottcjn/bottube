"""Security regression tests for bridge admin-key auth (fail-closed).

Covers the fix that removed the committed default key 'bottube_admin_key_2026'
and routed all admin checks through a constant-time, fail-closed helper.
"""
import importlib.util
import pathlib

import pytest

HERE = pathlib.Path(__file__).parent
MODULES = ["banano_blueprint", "ergo_bridge_blueprint", "base_wrtc_bridge_blueprint"]
OLD_LITERAL = "bottube_admin_key_2026"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # pragma: no cover - env-dependent optional deps
        pytest.skip(f"{name} not importable in this env: {exc}")
    return mod


@pytest.mark.parametrize("name", MODULES)
def test_unset_key_fails_closed(name):
    mod = _load(name)
    mod.ADMIN_KEY = ""  # simulate BOTTUBE_ADMIN_KEY unset
    # Nothing authenticates when the key is unset — including the old literal.
    assert mod._admin_ok("") is False
    assert mod._admin_ok(None) is False
    assert mod._admin_ok(OLD_LITERAL) is False
    assert mod._admin_ok("anything") is False


@pytest.mark.parametrize("name", MODULES)
def test_set_key_only_exact_match(name):
    mod = _load(name)
    mod.ADMIN_KEY = "real-secret-key-value"
    assert mod._admin_ok("real-secret-key-value") is True
    assert mod._admin_ok("") is False
    assert mod._admin_ok(None) is False
    assert mod._admin_ok("wrong") is False
    assert mod._admin_ok(OLD_LITERAL) is False


@pytest.mark.parametrize("name", MODULES)
def test_old_literal_not_present_in_source(name):
    src = (HERE / f"{name}.py").read_text(newline="")
    assert OLD_LITERAL not in src


def test_usdc_literal_removed():
    src = (HERE / "usdc_blueprint.py").read_text(newline="")
    assert OLD_LITERAL not in src


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
