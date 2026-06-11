# SPDX-License-Identifier: MIT
import os
import sqlite3
import sys
from pathlib import Path

import pytest
import werkzeug


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "test"


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_syndication_routes_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_syndication_routes_bootstrap.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    Path(bootstrap_path).unlink(missing_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server
import syndication_routes

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_syndication_routes.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test-admin", raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    syndication_routes.init_syndication(str(db_path))
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?)
            """,
            (agent_name, agent_name.title(), api_key, 1.0, 1.0),
        )
        db.commit()
        return int(cur.lastrowid)


def _tracker():
    return syndication_routes.get_tracker()


def test_update_item_requires_owner_scope(client):
    owner_id = _insert_agent("ownerbot", "bottube_sk_owner")
    intruder_id = _insert_agent("intruderbot", "bottube_sk_intruder")
    assert intruder_id != owner_id

    tracker = _tracker()
    run_id = tracker.start_run("x_crosspost", agent_id=owner_id)
    item_id = tracker.log_item(run_id, "video_owner_1", "pending", "x")

    denied = client.put(
        f"/api/syndication/item/{item_id}",
        headers={"X-API-Key": "bottube_sk_intruder"},
        json={"status": "success"},
    )
    assert denied.status_code == 403

    allowed = client.put(
        f"/api/syndication/item/{item_id}",
        headers={"X-API-Key": "bottube_sk_owner"},
        json={"status": "success", "external_id": "x_123"},
    )
    assert allowed.status_code == 200


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/syndication/run/start", ["run_type"]),
        ("post", "/api/syndication/run/1/end", ["status"]),
        ("post", "/api/syndication/item", ["run_id"]),
        ("put", "/api/syndication/item/1", ["status"]),
    ],
)
def test_write_routes_reject_non_object_json(client, method, path, payload):
    _insert_agent("jsonbot", "bottube_sk_jsonbot")

    resp = getattr(client, method)(
        path,
        headers={"X-API-Key": "bottube_sk_jsonbot"},
        json=payload,
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON body must be an object"}


def test_report_routes_scope_normal_agents_and_expand_for_admin(client):
    owner_id = _insert_agent("ownerreport", "bottube_sk_ownerreport")
    other_id = _insert_agent("otherreport", "bottube_sk_otherreport")
    tracker = _tracker()

    owner_run = tracker.start_run("x_crosspost", agent_id=owner_id)
    tracker.log_item(owner_run, "video_owner", "success", "x", external_id="x1")
    tracker.end_run(owner_run, "completed")

    other_run = tracker.start_run("rss_update", agent_id=other_id)
    tracker.log_item(other_run, "video_other", "failed", "rss", error_message="timeout")
    tracker.end_run(other_run, "partial")

    scoped = client.get(
        "/api/syndication/report/outbound?days=7",
        headers={"X-API-Key": "bottube_sk_ownerreport"},
    )
    assert scoped.status_code == 200
    scoped_report = scoped.get_json()["report"]
    assert scoped_report["scope"] == "agent"
    assert scoped_report["network_summary"]["total_runs"] == 1
    assert scoped_report["network_summary"]["active_agents"] == 1
    assert scoped_report["recent_failures"] == []

    admin = client.get(
        "/api/syndication/report/outbound?days=7&scope=network",
        headers={
            "X-API-Key": "bottube_sk_ownerreport",
            "X-Admin-Key": "test-admin",
        },
    )
    assert admin.status_code == 200
    admin_report = admin.get_json()["report"]
    assert admin_report["scope"] == "network"
    assert admin_report["network_summary"]["total_runs"] == 2
    assert admin_report["network_summary"]["active_agents"] == 2
    assert admin_report["network_summary"]["total_failures"] == 1


def test_export_route_returns_inline_json_without_file_path(client):
    owner_id = _insert_agent("exportbot", "bottube_sk_exportbot")
    tracker = _tracker()
    run_id = tracker.start_run("x_crosspost", agent_id=owner_id)
    tracker.log_item(run_id, "video_export", "success", "x", external_id="x_export")
    tracker.end_run(run_id, "completed")

    resp = client.get(
        "/api/syndication/report/export?type=outbound&days=7",
        headers={"X-API-Key": "bottube_sk_exportbot"},
    )
    assert resp.status_code == 200
    assert resp.is_json
    body = resp.get_json()
    assert body["ok"] is True
    assert body["scope"] == "agent"
    assert "file_path" not in body


@pytest.mark.parametrize(
    "path",
    [
        "/api/syndication/report/daily?date=not-a-date",
        "/api/syndication/report/weekly?end_date=not-a-date",
        "/api/syndication/report/export?type=daily&date=not-a-date",
        "/api/syndication/report/export?type=weekly&end_date=not-a-date",
    ],
)
def test_report_routes_reject_malformed_dates(client, path):
    _insert_agent("datebot", "bottube_sk_datebot")

    resp = client.get(
        path,
        headers={"X-API-Key": "bottube_sk_datebot"},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"].endswith("must use YYYY-MM-DD")
