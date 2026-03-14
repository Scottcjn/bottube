"""Homepage accessibility tests.

Task: #1618 - Report BoTTube UI accessibility issues
Task: #1589 - Write unit tests
"""
from __future__ import annotations
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, Generator

import pytest

ROOT: Path = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_homepage_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_homepage_bootstrap.db")

_orig_sqlite_connect: Callable = sqlite3.connect


def _bootstrap_sqlite_connect(path: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
    """Redirect database path for testing."""
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages

_orig_init_store_db: Callable = paypal_packages.init_store_db


def _test_init_store_db(db_path: str | None = None) -> None:
    """Initialize test database."""
    bootstrap_path: str = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    Path(bootstrap_path).unlink(missing_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[Any, None, None]:
    """Create test client with isolated database."""
    db_path: Path = tmp_path / "bottube_homepage.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def test_homepage_renders_friendly_category_chips_and_accessible_controls(
    client: Any,
) -> None:
    """Test homepage renders accessible category chips and controls."""
    resp: Any = client.get("/")
    assert resp.status_code == 200
    html: str = resp.get_data(as_text=True)

    assert "Browse AI Art videos" in html
    assert "🎨 AI Art" in html
    assert "trending?category=ai-art" in html
    assert "Copy pip install bottube command" in html
    assert "Three steps. Start uploading in minutes." in html
    assert "{{ cat }}" not in html
    assert "Three lines. That's it." not in html
