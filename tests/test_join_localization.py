"""Tests for /join page localization across supported locales."""

from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Generator

import pytest

ROOT: Path = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Bootstrap: redirect database path BEFORE importing bottube_server ─────
# bottube_server imports paypal_packages and calls init_gemini_tables()
# at module level, both of which try to open /root/bottube/bottube.db.
# We monkeypatch sqlite3.connect to redirect that path to a temp file so
# the import succeeds without touching the real filesystem.

_BOOTSTRAP_DB: str = tempfile.mktemp(suffix="_bottube_join_test.db", prefix="bottube_")
os.environ.setdefault("BOTTUBE_DB", _BOOTSTRAP_DB)
os.environ.setdefault("BOTTUBE_DB_PATH", _BOOTSTRAP_DB)

_orig_sqlite_connect: Callable = sqlite3.connect


def _bootstrap_connect(path: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
    """Redirect the hardcoded /root path to the bootstrap DB."""
    if str(path) == "/root/bottube/bottube.db":
        path = _BOOTSTRAP_DB
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_connect

import paypal_packages

_orig_init_store_db: Callable = paypal_packages.init_store_db


def _test_init_store_db(db_path: str | None = None) -> None:
    """Ensure store DB is also redirected for the test."""
    Path(_BOOTSTRAP_DB).parent.mkdir(parents=True, exist_ok=True)
    Path(_BOOTSTRAP_DB).unlink(missing_ok=True)
    return _orig_init_store_db(_BOOTSTRAP_DB)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server

sqlite3.connect = _orig_sqlite_connect

# ── Cleanup: remove the bootstrap DB after all tests in this module ─────


def _cleanup_bootstrap() -> None:
    try:
        Path(_BOOTSTRAP_DB).unlink(missing_ok=True)
    except OSError:
        pass


# ── Fixture ──────────────────────────────────────────────────────────────


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[Any, None, None]:
    """Create a test client with an isolated database."""
    db_path: Path = tmp_path / "bottube_join.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


# ── Helpers ──────────────────────────────────────────────────────────────


def _get(client: Any, locale: str | None) -> str:
    """GET /join and return the response body as text."""
    url = f"/join?lang={locale}" if locale else "/join"
    resp = client.get(url)
    assert resp.status_code == 200, f"GET {url} returned {resp.status_code}"
    return resp.get_data(as_text=True)


# ── Locale-specific hero_title assertions ────────────────────────────────

LOCALE_ASSERTIONS: dict[str, str] = {
    "es": "Únete a BoTTube",
    "fr": "Rejoignez BoTTube",
    "ja": "BoTTubeに参加",
    "pt": "Junte-se ao BoTTube",
}

ENGLISH_HERO: str = "Join BoTTube"


# ── Tests ────────────────────────────────────────────────────────────────


class TestJoinLocalization:
    """Regression tests for /join page i18n (issue #1712)."""

    def test_spanish_uses_translated_hero(self, client: Any) -> None:
        """GET /join?lang=es should contain the Spanish hero title."""
        html = _get(client, "es")
        assert LOCALE_ASSERTIONS["es"] in html, (
            f"Expected Spanish hero '{LOCALE_ASSERTIONS['es']}' not found"
        )

    def test_spanish_avoids_hardcoded_english(self, client: Any) -> None:
        """GET /join?lang=es should NOT contain the English hero title."""
        html = _get(client, "es")
        assert ENGLISH_HERO not in html, (
            f"Hardcoded English '{ENGLISH_HERO}' still present in Spanish response"
        )

    def test_french_uses_translated_hero(self, client: Any) -> None:
        """GET /join?lang=fr should contain the French hero title."""
        html = _get(client, "fr")
        assert LOCALE_ASSERTIONS["fr"] in html

    def test_japanese_uses_translated_hero(self, client: Any) -> None:
        """GET /join?lang=ja should contain the Japanese hero title."""
        html = _get(client, "ja")
        assert LOCALE_ASSERTIONS["ja"] in html

    def test_portuguese_uses_translated_hero(self, client: Any) -> None:
        """GET /join?lang=pt should contain the Portuguese hero title."""
        html = _get(client, "pt")
        assert LOCALE_ASSERTIONS["pt"] in html

    def test_english_fallback_when_no_lang(self, client: Any) -> None:
        """GET /join without lang param should default to English."""
        html = _get(client, None)
        assert ENGLISH_HERO in html, (
            f"English hero '{ENGLISH_HERO}' should appear when no lang param"
        )

    def test_html_lang_attribute_reflects_locale(self, client: Any) -> None:
        """GET /join?lang=es should have <html lang=\"es\">."""
        html = _get(client, "es")
        assert '<html lang="es">' in html, (
            "Expected <html lang=\"es\"> in response"
        )

    def test_html_lang_english_default(self, client: Any) -> None:
        """GET /join without lang param should default to <html lang=\"en\">."""
        html = _get(client, None)
        assert '<html lang="en">' in html, (
            "Expected <html lang=\"en\"> in response"
        )


class TestJoinTemplatesNoTranslationKeysLeaked:
    """Template-level checks: raw translation keys should not appear in output."""

    def test_no_raw_keys_in_spanish(self, client: Any) -> None:
        html = _get(client, "es")
        matches = re.findall(r"join\.\w+", html)
        assert not matches, f"Raw translation keys found in output: {matches}"

    def test_no_raw_keys_in_english(self, client: Any) -> None:
        html = _get(client, None)
        matches = re.findall(r"join\.\w+", html)
        assert not matches, f"Raw translation keys found in output: {matches}"


# ── Module-level cleanup ─────────────────────────────────────────────────
_cleanup_bootstrap()