import sys
import types

import pytest
from flask import Flask


@pytest.fixture
def beacon_client(monkeypatch):
    class FakeBeacon:
        beacon_id = "bcn_expected"

        def verify_identity(self, claimed_id):
            return claimed_id == self.beacon_id

    monkeypatch.setitem(
        sys.modules,
        "sophia_beacon",
        types.SimpleNamespace(get_beacon=lambda _agent_name: FakeBeacon()),
    )

    from agent_discovery import discovery_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(discovery_bp)
    return app.test_client()


def test_beacon_verify_rejects_non_object_json(beacon_client):
    resp = beacon_client.post("/api/beacon/verify", json="not-object")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON object required"}


def test_beacon_verify_rejects_non_string_agent_name(beacon_client):
    resp = beacon_client.post(
        "/api/beacon/verify",
        json={"agent_name": ["alice"], "beacon_id": "bcn_expected"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "agent_name must be a string"}


def test_beacon_verify_rejects_non_string_beacon_id(beacon_client):
    resp = beacon_client.post(
        "/api/beacon/verify",
        json={"agent_name": "alice", "beacon_id": ["bcn_expected"]},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "beacon_id must be a string"}


def test_beacon_verify_preserves_missing_field_error(beacon_client):
    resp = beacon_client.post("/api/beacon/verify", json={})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "agent_name and beacon_id required"}


def test_beacon_verify_validates_trimmed_strings(beacon_client):
    resp = beacon_client.post(
        "/api/beacon/verify",
        json={"agent_name": " alice ", "beacon_id": " bcn_expected "},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {
        "agent_name": "alice",
        "claimed_beacon": "bcn_expected",
        "verified": True,
        "expected_beacon": "bcn_expected",
    }
