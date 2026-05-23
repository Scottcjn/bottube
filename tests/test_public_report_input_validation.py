import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "BOTTUBE_DB_PATH",
    "/tmp/bottube_test_public_report_input_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_public_report_input_bootstrap.db",
)

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages  # noqa: E402


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server  # noqa: E402

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_public_report_input_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server._TS_SCHEMA_READY = False
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _report_count() -> int:
    with bottube_server.app.app_context():
        bottube_server._ensure_ts_schema()
        db = bottube_server.get_db()
        row = db.execute("SELECT COUNT(*) FROM moderation_reports").fetchone()
        return int(row[0])


def test_public_report_rejects_non_object_json(client):
    resp = client.post("/api/report", json=["not", "an", "object"])

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "JSON body must be an object",
    }
    assert _report_count() == 0


def test_public_report_rejects_falsy_non_object_json(client):
    resp = client.post("/api/report", json=[])

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "JSON body must be an object",
    }
    assert _report_count() == 0


def test_public_report_rejects_non_string_category_without_insert(client):
    resp = client.post(
        "/api/report",
        json={
            "category": ["spam"],
            "target": "https://bottube.ai/watch/abc123",
            "detail": "This report has enough detail.",
        },
    )

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "category must be a string",
    }
    assert _report_count() == 0


def test_public_report_rejects_non_string_email_without_insert(client):
    resp = client.post(
        "/api/report",
        json={
            "category": "spam",
            "target": "https://bottube.ai/watch/abc123",
            "detail": "This report has enough detail.",
            "email": {"address": "reporter@example.com"},
        },
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"ok": False, "error": "email must be a string"}
    assert _report_count() == 0


def test_public_report_null_fields_use_existing_required_validations(client):
    resp = client.post(
        "/api/report",
        json={"category": None, "target": None, "detail": None, "email": None},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"ok": False, "error": "invalid category"}
    assert _report_count() == 0


def test_public_report_still_accepts_valid_report(client):
    resp = client.post(
        "/api/report",
        json={
            "category": "spam",
            "target": "https://bottube.ai/watch/abc123",
            "detail": "This report has enough detail for review.",
            "email": "reporter@example.com",
        },
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["severity"] == "normal"
    assert _report_count() == 1
