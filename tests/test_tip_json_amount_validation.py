# SPDX-License-Identifier: MIT
"""Regression tests for RTC tip payload validation."""

import hashlib
import importlib
import time

import pytest


def _server():
    return importlib.import_module("bottube_server")


def _register(client, name):
    resp = client.post(
        "/api/register",
        json={
            "agent_name": name,
            "display_name": name.replace("_", " ").title(),
            "bio": "tip validation test",
        },
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _prepare(app, client, *, creator_wallet=""):
    bottube_server = _server()
    sender = _register(client, "tip_valid_sender")
    creator = _register(client, "tip_valid_creator")
    video_id = "tipvalidvid"

    with app.app_context():
        db = bottube_server.get_db()
        sender_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            (sender["agent_name"],),
        ).fetchone()["id"]
        creator_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            (creator["agent_name"],),
        ).fetchone()["id"]
        db.execute(
            "UPDATE agents SET rtc_balance = ? WHERE id = ?",
            (10.0, sender_id),
        )
        db.execute(
            "UPDATE agents SET rtc_balance = ?, rtc_wallet = ? WHERE id = ?",
            (0.0, creator_wallet, creator_id),
        )
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, description, filename, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (video_id, creator_id, "Tip validation video", "", "tipvalid.mp4", time.time()),
        )
        db.commit()

    return {
        "sender": sender,
        "sender_id": sender_id,
        "creator": creator,
        "creator_id": creator_id,
        "video_id": video_id,
    }


def _login(client, sender_id):
    with client.session_transaction() as sess:
        sess["user_id"] = sender_id
        sess["csrf_token"] = "test-csrf"


def _request_for(target, scenario):
    if target == "api_video":
        return {
            "path": f"/api/videos/{scenario['video_id']}/tip",
            "headers": {"X-API-Key": scenario["sender"]["api_key"]},
        }
    if target == "api_agent":
        return {
            "path": f"/api/agents/{scenario['creator']['agent_name']}/tip",
            "headers": {"X-API-Key": scenario["sender"]["api_key"]},
        }
    if target == "web_video":
        return {
            "path": f"/api/videos/{scenario['video_id']}/web-tip",
            "headers": {"X-CSRF-Token": "test-csrf"},
        }
    if target == "web_agent":
        return {
            "path": f"/api/agents/{scenario['creator']['agent_name']}/web-tip",
            "headers": {"X-CSRF-Token": "test-csrf"},
        }
    raise AssertionError(f"unknown target {target}")


def _balances(app, scenario):
    bottube_server = _server()
    with app.app_context():
        db = bottube_server.get_db()
        rows = db.execute(
            "SELECT id, rtc_balance FROM agents WHERE id IN (?, ?)",
            (scenario["sender_id"], scenario["creator_id"]),
        ).fetchall()
    return {r["id"]: r["rtc_balance"] for r in rows}


def _tip_count(app):
    bottube_server = _server()
    with app.app_context():
        db = bottube_server.get_db()
        return db.execute("SELECT COUNT(*) FROM tips").fetchone()[0]


@pytest.mark.parametrize("target", ["api_video", "api_agent", "web_video", "web_agent"])
def test_tip_handlers_reject_non_object_json_without_writes(app, client, target):
    scenario = _prepare(app, client)
    if target.startswith("web_"):
        _login(client, scenario["sender_id"])

    req = _request_for(target, scenario)
    before = _balances(app, scenario)

    resp = client.post(req["path"], json=["not", "an", "object"], headers=req["headers"])

    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"] == "JSON body must be an object"
    assert _balances(app, scenario) == before
    assert _tip_count(app) == 0


@pytest.mark.parametrize("target", ["api_video", "api_agent", "web_video", "web_agent"])
def test_tip_handlers_reject_boolean_amount_without_transferring(app, client, target):
    scenario = _prepare(app, client)
    if target.startswith("web_"):
        _login(client, scenario["sender_id"])

    req = _request_for(target, scenario)
    before = _balances(app, scenario)

    resp = client.post(req["path"], json={"amount": True}, headers=req["headers"])

    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"] == "Invalid amount"
    assert _balances(app, scenario) == before
    assert _tip_count(app) == 0


def test_onchain_tip_rejects_nan_amount_before_forwarding_to_rustchain(
    app, client, monkeypatch
):
    bottube_server = _server()
    public_key = "11" * 32
    from_address = f"RTC{hashlib.sha256(bytes.fromhex(public_key)).hexdigest()[:40]}"
    to_address = "RTC" + "a" * 40
    scenario = _prepare(app, client, creator_wallet=to_address)
    calls = []

    def fake_rustchain_post(path, payload, timeout=10.0):
        calls.append((path, payload, timeout))
        return 200, {"ok": True, "phase": "pending", "pending_id": 123, "tx_hash": "tx123"}

    monkeypatch.setattr(bottube_server, "_rustchain_post_json", fake_rustchain_post)

    resp = client.post(
        f"/api/agents/{scenario['creator']['agent_name']}/tip",
        json={
            "amount": "NaN",
            "onchain": True,
            "from_address": from_address,
            "to_address": to_address,
            "nonce": 1,
            "signature": "sig",
            "public_key": public_key,
            "memo": "tip",
        },
        headers={"X-API-Key": scenario["sender"]["api_key"]},
    )

    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"] == "Invalid amount"
    assert calls == []
    assert _tip_count(app) == 0
