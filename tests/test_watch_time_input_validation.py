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
    "/tmp/bottube_test_watch_time_input_bootstrap.db",
)
os.environ.setdefault(
    "BOTTUBE_DB",
    "/tmp/bottube_test_watch_time_input_bootstrap.db",
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


class FakeCTRTracker:
    def __init__(self):
        self.watch_times = []

    def record_watch_time(self, video_id, seconds):
        self.watch_times.append((video_id, seconds))


@pytest.fixture()
def tracker(monkeypatch):
    fake = FakeCTRTracker()
    monkeypatch.setattr(bottube_server, "_get_ctr_tracker", lambda: fake)
    return fake


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_watch_time_input_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def test_watch_time_rejects_non_object_json(client, tracker):
    resp = client.post("/api/videos/video123/watch_time", json=["bad"])

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "JSON body must be an object",
    }
    assert tracker.watch_times == []


def test_watch_time_rejects_falsy_non_object_json(client, tracker):
    resp = client.post("/api/videos/video123/watch_time", json=[])

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "JSON body must be an object",
    }
    assert tracker.watch_times == []


def test_watch_time_rejects_non_numeric_seconds(client, tracker):
    resp = client.post(
        "/api/videos/video123/watch_time",
        json={"seconds": "not-a-number"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "seconds must be a number",
    }
    assert tracker.watch_times == []


def test_watch_time_rejects_negative_seconds(client, tracker):
    resp = client.post(
        "/api/videos/video123/watch_time",
        json={"seconds": -5},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "seconds must be non-negative",
    }
    assert tracker.watch_times == []


def test_watch_time_rejects_non_finite_seconds(client, tracker):
    resp = client.post(
        "/api/videos/video123/watch_time",
        json={"seconds": "NaN"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "seconds must be finite",
    }
    assert tracker.watch_times == []


def test_watch_time_null_seconds_is_noop(client, tracker):
    resp = client.post(
        "/api/videos/video123/watch_time",
        json={"seconds": None},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {
        "ok": True,
        "video_id": "video123",
        "seconds_recorded": 0.0,
    }
    assert tracker.watch_times == []


def test_watch_time_records_positive_seconds(client, tracker):
    resp = client.post(
        "/api/videos/video123/watch_time",
        json={"seconds": "12.5"},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {
        "ok": True,
        "video_id": "video123",
        "seconds_recorded": 12.5,
    }
    assert tracker.watch_times == [("video123", 12.5)]
