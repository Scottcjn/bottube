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
    "/tmp/bottube_test_public_utility_json_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_public_utility_json_bootstrap.db",
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
def client(monkeypatch):
    def fail_get_db():
        raise AssertionError("invalid public utility input must not touch the DB")

    monkeypatch.setattr(bottube_server, "get_db", fail_get_db)
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


@pytest.mark.parametrize(
    "path",
    ["/api/push/unsubscribe", "/api/track/miner-install"],
)
def test_public_utility_endpoints_reject_non_object_json(client, path):
    resp = client.post(path, json=["bad"])

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "JSON body must be an object",
    }


def test_push_unsubscribe_rejects_non_string_endpoint(client):
    resp = client.post("/api/push/unsubscribe", json={"endpoint": ["bad"]})

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "endpoint must be a string",
    }


def test_miner_install_tracking_rejects_non_string_fields(client):
    resp = client.post(
        "/api/track/miner-install",
        json={"source": ["pip"], "page": {"path": "/miner"}},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "source must be a string",
    }
