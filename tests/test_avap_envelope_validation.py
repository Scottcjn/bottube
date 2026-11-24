# SPDX-License-Identifier: MIT
"""Regression coverage for malformed AVAP envelope payloads."""

import hashlib
import json
import sqlite3

import pytest
from flask import Flask
from nacl.signing import SigningKey

import avap_blueprint


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "bottube.db"
    monkeypatch.setattr(avap_blueprint, "DB_PATH", db_path)
    avap_blueprint.init_avap_tables()

    app = Flask(__name__)
    app.config["TESTING"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.register_blueprint(avap_blueprint.avap_bp)

    test_client = app.test_client()
    test_client.db_path = db_path
    return test_client


def _envelope_count(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM avap_envelopes").fetchone()[0]
    finally:
        conn.close()


def _signed_envelope(**overrides):
    signing_key = SigningKey.generate()
    pub_hex = signing_key.verify_key.encode().hex()
    addr = "RTC" + hashlib.sha256(bytes.fromhex(pub_hex)).hexdigest()[:40]
    env = {
        "avap": avap_blueprint.AVAP_VERSION,
        "type": "video_attestation",
        "recipient": "bottube",
        "sender": {"address": addr, "public_key": pub_hex},
    }
    env.update(overrides)
    core = json.dumps(env, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    commitment = hashlib.sha256(core).hexdigest()
    sig = signing_key.sign(core).signature.hex()
    env["anchor"] = {"commitment": commitment}
    env["sig"] = sig
    return env, commitment


def test_verify_envelope_handles_malformed_structures():
    bad_inputs = [
        None,
        ["not-a-dict"],
        {"avap": "1.0", "sender": "alice"},
        {"avap": "1.0", "sender": ["alice"]},
        {"avap": "1.0", "sender": {"public_key": 123, "address": "RTC123"}},
        {"avap": "1.0", "sender": {"public_key": "not-hex", "address": "RTC123"}},
        {"avap": "1.0", "sender": {"public_key": "abcd", "address": "RTC123"}, "anchor": "bad"},
        {
            "avap": "1.0",
            "sender": {
                "public_key": "00" * 32,
                "address": "RTC" + hashlib.sha256(b"\x00" * 32).hexdigest()[:40],
            },
            "sig": 999,
        },
    ]

    for payload in bad_inputs:
        res = avap_blueprint.verify_envelope(payload)
        assert res["ok"] is False
        assert res["checks"]["signature"] is False


def test_avap_attach_rejects_malformed_fields_without_500(client):
    valid_pub = "11" * 32
    valid_addr = "RTC" + hashlib.sha256(bytes.fromhex(valid_pub)).hexdigest()[:40]

    malformed_envelopes = [
        {"avap": "1.0", "sender": "alice"},
        {"avap": "1.0", "sender": 42},
        {"avap": "1.0", "sender": {"public_key": "not-hex", "address": "RTCabc"}},
        {"avap": "1.0", "sender": {"public_key": ["11"], "address": valid_addr}},
        {"avap": "1.0", "sender": {"public_key": valid_pub, "address": valid_addr}, "anchor": "bad"},
        {"avap": "1.0", "sender": {"public_key": valid_pub, "address": valid_addr}, "sig": 12345},
        {"avap": "1.0", "sender": {"public_key": valid_pub, "address": valid_addr}, "sig": ["deadbeef"]},
        {"avap": "1.0", "sender": {"public_key": valid_pub, "address": valid_addr}, "sig": "not-hex"},
    ]

    for payload in malformed_envelopes:
        resp = client.post("/api/video/vid-1/avap", json=payload)
        assert resp.status_code == 422
        assert resp.get_json()["error"] == "envelope failed verification"

    assert _envelope_count(client.db_path) == 0


def test_avap_attach_rejects_non_string_sqlite_columns_with_400(client):
    bad_recipient_env, _ = _signed_envelope(recipient={"agent": "bob"})
    resp = client.post("/api/video/vid-2/avap", json=bad_recipient_env)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "recipient must be a string"}

    bad_type_env, _ = _signed_envelope(type=["attestation"])
    resp = client.post("/api/video/vid-3/avap", json=bad_type_env)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "type must be a string"}

    assert _envelope_count(client.db_path) == 0


def test_avap_attach_valid_signed_envelope_succeeds_and_fetches(client):
    env, commitment = _signed_envelope(recipient=None)
    post_resp = client.post("/api/video/vid-ok/avap", json=env)
    assert post_resp.status_code == 200
    body = post_resp.get_json()
    assert body == {
        "ok": True,
        "commitment": commitment,
        "checks": {
            "version": True,
            "address_binding": True,
            "commitment": True,
            "signature": True,
        },
        "video_id": "vid-ok",
    }

    get_resp = client.get("/api/video/vid-ok/avap")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["anchor"]["commitment"] == commitment
    assert _envelope_count(client.db_path) == 1
