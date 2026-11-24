# SPDX-License-Identifier: MIT
"""Regression tests for rtc_services, studio_blueprint, and whisper_blueprint."""

import hashlib
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def rtc_app(tmp_path):
    import rtc_services

    db_path = tmp_path / "rtc_use_race.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            rtc_balance REAL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            reason TEXT DEFAULT '',
            video_id TEXT DEFAULT '',
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO agents (agent_name, api_key, rtc_balance) VALUES (?, ?, ?)",
        ("spender", "bottube_sk_spender", 200.0),
    )
    conn.commit()
    conn.close()

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    rtc_services.init_app(flask_app, db_path)
    flask_app.config["RTC_TEST_DB"] = str(db_path)
    return flask_app


def _purchase_row(app, raw_token: str):
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    conn = sqlite3.connect(app.config["RTC_TEST_DB"])
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT status, uses_remaining, redeemed_at "
            "FROM service_purchases WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
    finally:
        conn.close()


def test_rtc_use_concurrent_single_use_prevents_double_spend(rtc_app):
    client = rtc_app.test_client()
    pay_resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "render_standard", "quantity": 1},
        headers={"X-API-Key": "bottube_sk_spender"},
    )
    assert pay_resp.status_code == 200
    token = pay_resp.get_json()["service_token"]

    workers = 10
    barrier = threading.Barrier(workers)
    results = []
    lock = threading.Lock()

    def use_once():
        local_client = rtc_app.test_client()
        barrier.wait()
        resp = local_client.post("/api/rtc/use", json={"service_token": token})
        with lock:
            results.append((resp.status_code, resp.get_json()))

    threads = [threading.Thread(target=use_once) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    ok_calls = [(code, body) for code, body in results if code == 200]
    rejected = [code for code, _ in results if code != 200]

    assert len(ok_calls) == 1
    assert ok_calls[0][1]["uses_remaining"] == 0
    assert all(code in (404, 410) for code in rejected)

    row = _purchase_row(rtc_app, token)
    assert row["uses_remaining"] == 0
    assert row["status"] == "exhausted"


def test_rtc_use_concurrent_multi_use_conserves_exact_uses(rtc_app):
    client = rtc_app.test_client()
    pay_resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "render_variant", "quantity": 3},
        headers={"X-API-Key": "bottube_sk_spender"},
    )
    assert pay_resp.status_code == 200
    token = pay_resp.get_json()["service_token"]

    workers = 9
    barrier = threading.Barrier(workers)
    results = []
    lock = threading.Lock()

    def use_once():
        local_client = rtc_app.test_client()
        barrier.wait()
        resp = local_client.post("/api/rtc/use", json={"service_token": token})
        with lock:
            results.append((resp.status_code, resp.get_json()))

    threads = [threading.Thread(target=use_once) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    ok_remaining = sorted(
        body["uses_remaining"] for code, body in results if code == 200
    )
    assert ok_remaining == [0, 1, 2]
    assert all(code in (404, 410) for code, _ in results if code != 200)

    row = _purchase_row(rtc_app, token)
    assert row["uses_remaining"] == 0
    assert row["status"] == "exhausted"


def test_rtc_use_expired_token_returns_410_without_decrementing(rtc_app):
    client = rtc_app.test_client()
    pay_resp = client.post(
        "/api/rtc/pay",
        json={"service_key": "inference_single", "quantity": 1},
        headers={"X-API-Key": "bottube_sk_spender"},
    )
    assert pay_resp.status_code == 200
    token = pay_resp.get_json()["service_token"]
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    conn = sqlite3.connect(rtc_app.config["RTC_TEST_DB"])
    conn.execute(
        "UPDATE service_purchases SET expires_at = ? WHERE token_hash = ?",
        (time.time() - 10, token_hash),
    )
    conn.commit()
    conn.close()

    resp = client.post("/api/rtc/use", json={"service_token": token})
    assert resp.status_code == 410
    assert resp.get_json() == {"error": "Token expired"}

    row = _purchase_row(rtc_app, token)
    assert row["uses_remaining"] == 1
    assert row["status"] == "expired"


def test_rtc_pay_rejects_infinity_quantity_without_500(rtc_app):
    client = rtc_app.test_client()
    resp = client.post(
        "/api/rtc/pay",
        data='{"service_key": "pro_api_day", "quantity": 1e309}',
        content_type="application/json",
        headers={"X-API-Key": "bottube_sk_spender"},
    )
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "quantity must be an integer"}


@pytest.mark.parametrize(
    "bad_seconds",
    [
        "inf",
        "-inf",
        "Infinity",
        "-Infinity",
        float("inf"),
        float("-inf"),
        "nan",
        float("nan"),
        True,
        10**400,
    ],
)
def test_studio_video_cost_handles_non_finite_and_overflow_inputs(bad_seconds):
    import studio_blueprint as sb

    default_sec = sb.VIDEO_TIERS["text_card"]["default_s"]
    expected_cost = round(sb.VIDEO_TIERS["text_card"]["rtc_per_sec"] * default_sec, 2)
    cost, seconds = sb._video_cost("text_card", bad_seconds)
    assert (cost, seconds) == (expected_cost, default_sec)


def test_studio_generate_does_not_500_on_infinite_seconds():
    import studio_blueprint as sb

    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.register_blueprint(sb.studio_bp)
    client = app.test_client()

    for raw in (
        '{"type":"video","tier":"text_card","prompt":"hello","seconds":"inf"}',
        '{"type":"video","tier":"text_card","prompt":"hello","seconds":"-inf"}',
        '{"type":"video","tier":"text_card","prompt":"hello","seconds":1e309}',
    ):
        resp = client.post(
            "/api/studio/generate",
            data=raw,
            content_type="application/json",
        )
        assert resp.status_code == 401


def test_whisper_trigger_requires_admin_and_blocks_anonymous_enqueue(
    tmp_path, monkeypatch
):
    import whisper_transcription as wt
    import whisper_transcription_blueprint as wtb

    db_file = tmp_path / "whisper_auth.db"
    monkeypatch.setattr(wt, "_get_db_path", lambda: str(db_file))
    wt.init_transcription_tables()
    monkeypatch.setattr(wtb, "_get_video_filename", lambda _vid: "clip.mp4")

    enqueued = []
    monkeypatch.setattr(
        wtb.wt,
        "enqueue_transcription",
        lambda *args, **kwargs: enqueued.append((args, kwargs)),
    )

    app = Flask(__name__)
    app.register_blueprint(wtb.whisper_bp)
    app.config["TESTING"] = True
    client = app.test_client()

    # Unauthenticated request must fail closed with 403 and never enqueue work.
    anon = client.post("/api/videos/clip/transcript/trigger", json={"force": True})
    assert anon.status_code == 403
    assert enqueued == []

    # Invalid admin key must also fail closed.
    bad_admin = client.post(
        "/api/videos/clip/transcript/trigger",
        json={"force": True},
        headers={"X-Admin-Key": "wrong-key"},
    )
    assert bad_admin.status_code == 403
    assert enqueued == []

    # Authorized admin succeeds cleanly.
    monkeypatch.setattr(wtb, "_require_admin", lambda: None)
    ok = client.post("/api/videos/clip/transcript/trigger", json={"force": True})
    assert ok.status_code == 202
    assert ok.get_json()["force"] is True
    assert len(enqueued) == 1


@pytest.mark.parametrize("bad_force", ["false", "true", 0, 1, [], {}, None])
def test_whisper_backfill_rejects_non_boolean_force(tmp_path, monkeypatch, bad_force):
    import whisper_transcription as wt
    import whisper_transcription_blueprint as wtb

    db_file = tmp_path / "whisper_backfill.db"
    monkeypatch.setattr(wt, "_get_db_path", lambda: str(db_file))
    wt.init_transcription_tables()
    monkeypatch.setattr(wtb, "_require_admin", lambda: None)
    monkeypatch.setattr(
        wtb.wt,
        "backfill_existing_videos",
        lambda **_kw: pytest.fail("invalid force reached backfill_existing_videos"),
    )

    app = Flask(__name__)
    app.register_blueprint(wtb.whisper_bp)
    app.config["TESTING"] = True
    client = app.test_client()

    resp = client.post("/api/transcript/backfill", json={"force": bad_force})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "force must be a boolean"}
