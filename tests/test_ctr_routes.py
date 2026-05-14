from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Generator

import pytest


ROOT = Path(__file__).resolve().parents[1]


class FakeCTRTracker:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def get_top_by_ctr(self, *, limit: int, min_impressions: int) -> list[dict[str, int | str]]:
        self.calls.append((limit, min_impressions))
        return [{"video_id": f"vid-{idx}", "impressions": min_impressions} for idx in range(limit)]


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[Any, None, None]:
    db_path = tmp_path / "bottube_ctr_routes.db"
    os.environ["BOTTUBE_BASE_DIR"] = str(tmp_path)
    os.environ["BOTTUBE_DB_PATH"] = str(db_path)
    os.environ["BOTTUBE_DB"] = str(db_path)

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    for mod_name in list(sys.modules.keys()):
        if mod_name == "bottube_server" or mod_name.endswith("_blueprint") or mod_name in {
            "paypal_packages",
            "gpu_marketplace",
            "banano_blueprint",
            "captions_blueprint",
        }:
            del sys.modules[mod_name]

    orig_connect = sqlite3.connect

    def redirect_root_db(path: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        if str(path) == "/root/bottube/bottube.db":
            path = db_path
        return orig_connect(path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", redirect_root_db)

    import bottube_server

    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def test_ctr_top_clamps_negative_limit_to_lower_bound(client, monkeypatch):
    import bottube_server

    tracker = FakeCTRTracker()
    monkeypatch.setattr(bottube_server, "_get_ctr_tracker", lambda: tracker)

    resp = client.get("/api/ctr/top?limit=-1&min_impressions=1")

    assert resp.status_code == 200
    assert tracker.calls == [(1, 1)]
    assert len(resp.get_json()["videos"]) == 1


def test_ctr_top_keeps_existing_upper_bound(client, monkeypatch):
    import bottube_server

    tracker = FakeCTRTracker()
    monkeypatch.setattr(bottube_server, "_get_ctr_tracker", lambda: tracker)

    resp = client.get("/api/ctr/top?limit=500&min_impressions=1")

    assert resp.status_code == 200
    assert tracker.calls == [(50, 1)]
    assert len(resp.get_json()["videos"]) == 50
