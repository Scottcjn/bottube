# SPDX-License-Identifier: MIT
"""Bridge blueprints must open the same database their tables were made in.

`bottube_server` creates the usdc / wrtc / base-wrtc / ergo tables using
`os.environ.get("BOTTUBE_DB_PATH", str(DB_PATH))` (lines 15463-15490),
while each of those blueprints resolved its runtime connection with
`os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")`.

Two names and two defaults, so unless an operator set *both* variables to
the same value the bridges talked to a different file than the one holding
their tables — the tables would be missing, or worse, present in a stale
second database with different agent rows and balances.
"""

import importlib
from pathlib import Path

import pytest

from bottube_db import resolve_db_path

BRIDGES = [
    "usdc_blueprint",
    "ergo_bridge_blueprint",
    "wrtc_bridge_blueprint",
    "base_wrtc_bridge_blueprint",
]

# Two more live blueprints resolved a database path of their own. Neither was
# part of the init/runtime mismatch above, but both were worse in their own
# way: news_routes hardcoded the path with no override at all, and
# avap_blueprint recomputed BASE_DIR without honouring BOTTUBE_BASE_DIR, so it
# ignored the very variable bottube_server uses.
OTHER_DB_USERS = ["news_routes", "avap_blueprint"]


def _server_init_path(monkeypatch_env, base_dir):
    """What bottube_server uses when creating the bridge tables.

    After the fix this is the shared resolver; before it, it was
    ``os.environ.get("BOTTUBE_DB_PATH", str(DB_PATH))`` inline.
    """
    return resolve_db_path()


def test_db_path_prefers_the_server_variable(monkeypatch):
    monkeypatch.setenv("BOTTUBE_DB_PATH", "/data/from-server.db")
    monkeypatch.setenv("BOTTUBE_DB", "/data/from-bridge.db")

    assert resolve_db_path() == "/data/from-server.db"


def test_db_path_accepts_the_legacy_bridge_variable(monkeypatch):
    monkeypatch.delenv("BOTTUBE_DB_PATH", raising=False)
    monkeypatch.setenv("BOTTUBE_DB", "/data/legacy.db")

    assert resolve_db_path() == "/data/legacy.db"


def test_db_path_defaults_next_to_the_app_not_to_root(monkeypatch, tmp_path):
    """The old default was a hardcoded /root path, wrong on any other install."""
    monkeypatch.delenv("BOTTUBE_DB_PATH", raising=False)
    monkeypatch.delenv("BOTTUBE_DB", raising=False)
    monkeypatch.setenv("BOTTUBE_BASE_DIR", str(tmp_path))

    resolved = resolve_db_path()

    assert resolved == str(tmp_path / "bottube.db")
    assert not resolved.startswith("/root/"), "still hardcoding /root"


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"BOTTUBE_DB_PATH": "/data/x.db"},
        {"BOTTUBE_DB": "/data/x.db"},
        {"BOTTUBE_DB_PATH": "/data/x.db", "BOTTUBE_DB": "/data/x.db"},
    ],
    ids=["neither", "server-var-only", "bridge-var-only", "both"],
)
def test_bridge_and_server_agree_in_every_configuration(monkeypatch, tmp_path, env):
    monkeypatch.delenv("BOTTUBE_DB_PATH", raising=False)
    monkeypatch.delenv("BOTTUBE_DB", raising=False)
    monkeypatch.setenv("BOTTUBE_BASE_DIR", str(tmp_path))
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    server_path = _server_init_path(env, tmp_path)
    bridge_path = resolve_db_path()

    assert bridge_path == server_path, (
        f"bridge would open {bridge_path} but its tables live in {server_path}"
    )


@pytest.mark.parametrize("module_name", BRIDGES)
def test_no_bridge_hardcodes_the_root_path(module_name):
    src = Path(f"{module_name}.py").read_text(encoding="utf-8", errors="replace")

    assert '"BOTTUBE_DB", "/root/bottube/bottube.db"' not in src
    assert "'BOTTUBE_DB', '/root/bottube/bottube.db'" not in src


@pytest.mark.parametrize("module_name", BRIDGES)
def test_bridges_import_the_shared_resolver(module_name):
    module = importlib.import_module(module_name)

    assert hasattr(module, "resolve_db_path"), (
        f"{module_name} does not use the shared resolver"
    )


@pytest.mark.parametrize("module_name", OTHER_DB_USERS)
def test_other_blueprints_do_not_hardcode_a_database_path(module_name):
    src = Path(f"{module_name}.py").read_text(encoding="utf-8", errors="replace")

    assert "/root/bottube/bottube.db" not in src, (
        f"{module_name} still hardcodes an absolute database path"
    )


@pytest.mark.parametrize("module_name", OTHER_DB_USERS)
def test_other_blueprints_use_the_shared_resolver(module_name):
    module = importlib.import_module(module_name)

    assert hasattr(module, "resolve_db_path"), (
        f"{module_name} does not use the shared resolver"
    )


def test_avap_honours_base_dir_override(monkeypatch, tmp_path):
    """avap_blueprint used to recompute BASE_DIR and ignore BOTTUBE_BASE_DIR."""
    monkeypatch.delenv("BOTTUBE_DB_PATH", raising=False)
    monkeypatch.delenv("BOTTUBE_DB", raising=False)
    monkeypatch.setenv("BOTTUBE_BASE_DIR", str(tmp_path))

    assert resolve_db_path() == str(tmp_path / "bottube.db")
