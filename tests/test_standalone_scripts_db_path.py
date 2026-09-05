# SPDX-License-Identifier: MIT
"""banano_payout.py and bottube_engage.py are cron/standalone scripts, not
Flask blueprints — they used to resolve their own DB_PATH straight from
os.environ.get("BOTTUBE_DB", ...), independently of the shared
bottube_db.resolve_db_path() precedence (BOTTUBE_DB_PATH -> BOTTUBE_DB ->
BOTTUBE_BASE_DIR) the rest of the codebase was already unified onto in the
bridge/gemini/news fixes. On a BOTTUBE_DB_PATH-only deployment (the name the
main server and table-creation code actually use) both scripts silently fell
back to the hardcoded /root/bottube/bottube.db default instead of the
configured path -- the payout cron would read a bottube.db with none of the
server's tables, and the engagement script would post replies sourced from
the wrong (likely empty) database.
"""
import importlib


def _reload(module_name):
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_banano_payout_prefers_bottube_db_path(tmp_path, monkeypatch):
    configured = tmp_path / "configured.db"
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(configured))
    monkeypatch.setenv("BOTTUBE_DB", str(tmp_path / "legacy-should-be-ignored.db"))

    module = _reload("banano_payout")
    assert module.DB_PATH == str(configured)


def test_banano_payout_falls_back_to_legacy_bottube_db(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.db"
    monkeypatch.delenv("BOTTUBE_DB_PATH", raising=False)
    monkeypatch.setenv("BOTTUBE_DB", str(legacy))

    module = _reload("banano_payout")
    assert module.DB_PATH == str(legacy)


def test_bottube_engage_prefers_bottube_db_path(tmp_path, monkeypatch):
    configured = tmp_path / "configured.db"
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(configured))
    monkeypatch.setenv("BOTTUBE_DB", str(tmp_path / "legacy-should-be-ignored.db"))

    module = _reload("bottube_engage")
    assert module.DB_PATH == str(configured)


def test_bottube_engage_falls_back_to_legacy_bottube_db(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.db"
    monkeypatch.delenv("BOTTUBE_DB_PATH", raising=False)
    monkeypatch.setenv("BOTTUBE_DB", str(legacy))

    module = _reload("bottube_engage")
    assert module.DB_PATH == str(legacy)
