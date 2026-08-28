# SPDX-License-Identifier: MIT
"""Regression tests validating JSON payload parsing and finite amount checks on RTC tip endpoints (#1786)."""
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
    tempfile.gettempdir(), "bottube_test_tip_validation_bootstrap.db"
)
os.environ.setdefault("BOTTUBE_DB", _BOOTSTRAP_DB)
os.environ.setdefault("BOTTUBE_DB_PATH", _BOOTSTRAP_DB)

import bottube_server


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_tip_validation.db"
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
        "agent_name": name, "display_name": name, "bio": "tip validation test",
    })
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


@pytest.fixture()
def scenario(client):
    tipper = _register(client, "tip_val_sender")
    creator = _register(client, "tip_val_creator")

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        creator_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (creator["agent_name"],)
        ).fetchone()["id"]
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, description, filename, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("tipvalvid", creator_id, "Tip Validation Video", "", "tipvalvid.mp4", time.time()),
        )
        # Fund tipper with 50 RTC
        db.execute("UPDATE agents SET rtc_balance = 50.0 WHERE agent_name = ?", (tipper["agent_name"],))
        db.commit()

    return {"tipper": tipper, "creator": creator, "video_id": "tipvalvid"}


def test_tip_video_rejects_non_object_json(client, scenario):
    headers = {"X-API-Key": scenario["tipper"]["api_key"], "Content-Type": "application/json"}
    resp = client.post(f"/api/videos/{scenario['video_id']}/tip", data="[1, 2, 3]", headers=headers)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Request body must be a JSON object"}


def test_tip_video_rejects_boolean_amount(client, scenario):
    headers = {"X-API-Key": scenario["tipper"]["api_key"], "Content-Type": "application/json"}
    resp = client.post(f"/api/videos/{scenario['video_id']}/tip", json={"amount": True}, headers=headers)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Invalid amount"}


def test_tip_video_rejects_nan_and_inf(client, scenario):
    headers = {"X-API-Key": scenario["tipper"]["api_key"], "Content-Type": "application/json"}
    resp = client.post(f"/api/videos/{scenario['video_id']}/tip", data='{"amount": NaN}', headers=headers)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Invalid amount"}

    resp = client.post(f"/api/videos/{scenario['video_id']}/tip", data='{"amount": Infinity}', headers=headers)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Invalid amount"}


def test_tip_agent_rejects_malformed_and_accepts_valid(client, scenario):
    headers = {"X-API-Key": scenario["tipper"]["api_key"], "Content-Type": "application/json"}
    resp = client.post(f"/api/agents/{scenario['creator']['agent_name']}/tip", json={"amount": False}, headers=headers)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Invalid amount"}

    resp = client.post(f"/api/agents/{scenario['creator']['agent_name']}/tip", data='"not a dict"', headers=headers)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Request body must be a JSON object"}

    resp = client.post(
        f"/api/agents/{scenario['creator']['agent_name']}/tip",
        json={"amount": 1.5, "message": "Awesome work"},
        headers=headers
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert resp.get_json()["amount"] == 1.5
