# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for malformed AVAP anchor request bodies."""

import sqlite3

import pytest
from flask import Flask

import avap_blueprint


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "bottube.db"
    monkeypatch.setattr(avap_blueprint, "DB_PATH", db_path)
    avap_blueprint.init_avap_tables()

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(avap_blueprint.avap_bp)

    test_client = app.test_client()
    test_client.db_path = db_path
    return test_client


def _anchor_count(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM avap_anchors").fetchone()[0]
    finally:
        conn.close()


def test_avap_anchor_rejects_non_object_json(client):
    for payload in (["bad"], "bad", 5, True):
        resp = client.post("/avap/anchor", json=payload)

        assert resp.status_code == 400
        assert resp.get_json() == {"error": "JSON body must be an object"}

    assert _anchor_count(client.db_path) == 0


def test_avap_anchor_rejects_non_string_fields(client):
    valid_commitment = "a" * 64

    cases = [
        ({"commitment": 7}, {"error": "commitment must be a string"}),
        (
            {"commitment": valid_commitment, "video_id": ["video"]},
            {"error": "video_id must be a string"},
        ),
        (
            {"commitment": valid_commitment, "sender": {"address": "RTC123"}},
            {"error": "sender must be a string"},
        ),
    ]

    for payload, expected in cases:
        resp = client.post("/avap/anchor", json=payload)

        assert resp.status_code == 400
        assert resp.get_json() == expected

    assert _anchor_count(client.db_path) == 0


def test_avap_anchor_valid_request_and_duplicate_still_work(client):
    commitment = "A" * 64

    resp = client.post(
        "/avap/anchor",
        json={"commitment": commitment, "video_id": "vid-1", "sender": "RTCabc"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["commitment"] == commitment.lower()
    assert body["tx"] == "rc2:" + commitment.lower()[:32]
    assert "duplicate" not in body

    duplicate = client.post("/avap/anchor", json={"commitment": commitment.lower()})
    assert duplicate.status_code == 200
    duplicate_body = duplicate.get_json()
    assert duplicate_body["commitment"] == commitment.lower()
    assert duplicate_body["duplicate"] is True
    assert duplicate_body["tx"] == body["tx"]

    assert _anchor_count(client.db_path) == 1
