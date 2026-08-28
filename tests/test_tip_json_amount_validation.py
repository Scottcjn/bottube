# SPDX-License-Identifier: MIT
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_BOOTSTRAP_DB = os.path.join(
    tempfile.gettempdir(), "bottube_test_tip_json_validation_bootstrap.db"
)
os.environ.setdefault("BOTTUBE_DB", _BOOTSTRAP_DB)
os.environ.setdefault("BOTTUBE_DB_PATH", _BOOTSTRAP_DB)

import bottube_server  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_tip_json_validation.db"
    video_dir = tmp_path / "videos"
    thumb_dir = tmp_path / "thumbnails"
    avatar_dir = tmp_path / "avatars"
    for d in (video_dir, thumb_dir, avatar_dir):
        d.mkdir()

    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "VIDEO_DIR", video_dir, raising=False)
    monkeypatch.setattr(bottube_server, "THUMB_DIR", thumb_dir, raising=False)
    monkeypatch.setattr(bottube_server, "AVATAR_DIR", avatar_dir, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0

    with bottube_server.app.app_context():
        bottube_server.init_db()

    bottube_server.app.config["TESTING"] = True
    return bottube_server.app.test_client()


def _register(client, name):
    resp = client.post("/api/register", json={
        "agent_name": name, "display_name": name, "bio": "tip validation",
    })
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


@pytest.fixture()
def scenario(client):
    tipper = _register(client, "tip_json_sender")
    creator = _register(client, "tip_json_creator")

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        creator_row = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (creator["agent_name"],)
        ).fetchone()
        tipper_row = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (tipper["agent_name"],)
        ).fetchone()
        db.execute(
            "UPDATE agents SET rtc_balance = 10 WHERE id = ?", (tipper_row["id"],)
        )
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, description, filename, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("tipjsonvid", creator_row["id"], "Tip JSON Video", "", "tipjsonvid.mp4", time.time()),
        )
        db.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = tipper_row["id"]
        sess["csrf_token"] = "test-csrf"

    return {
        "tipper": tipper,
        "creator": creator,
        "video_id": "tipjsonvid",
        "csrf": {"X-CSRF-Token": "test-csrf"},
    }


@pytest.mark.parametrize("path", [
    "/api/videos/tipjsonvid/tip",
    "/api/videos/tipjsonvid/web-tip",
    "/api/agents/tip_json_creator/tip",
    "/api/agents/tip_json_creator/web-tip",
])
def test_tip_routes_reject_non_object_json(client, scenario, path):
    headers = {}
    if "/api/" in path and path.endswith("/tip") and "/web-tip" not in path:
        headers["X-API-Key"] = scenario["tipper"]["api_key"]
    else:
        headers.update(scenario["csrf"])

    resp = client.post(path, json=["bad"], headers=headers)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "JSON body must be an object"


@pytest.mark.parametrize("bad_amount", [True, False, "oops", float("nan"), float("inf"), -float("inf")])
def test_api_video_tip_rejects_invalid_amount_types(client, scenario, bad_amount):
    resp = client.post(
        f"/api/videos/{scenario['video_id']}/tip",
        json={"amount": bad_amount},
        headers={"X-API-Key": scenario["tipper"]["api_key"]},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid amount"


def test_web_agent_tip_accepts_valid_numeric_amount(client, scenario):
    resp = client.post(
        f"/api/agents/{scenario['creator']['agent_name']}/web-tip",
        json={"amount": 1, "message": "дякую"},
        headers=scenario["csrf"],
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["ok"] is True
    assert body["amount"] == 1.0
