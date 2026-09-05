# SPDX-License-Identifier: MIT
from flask import Flask

import scraper_detective
from scraper_detective import scraper_bp


class FakeDetective:
    def __init__(self):
        self.proofs = []
        self._js_proof = {}

    def record_js_proof(self, ip):
        self.proofs.append(ip)
        self._js_proof[ip] = {
            "proved": True,
            "proved_at": 1.0,
            "page_views": 0,
        }


def _client(monkeypatch):
    fake = FakeDetective()
    monkeypatch.setattr(scraper_detective, "detective", fake)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(scraper_bp)
    return app.test_client(), fake


def test_bt_proof_accepts_non_object_json_without_crashing(monkeypatch):
    """Verify /api/bt-proof does not crash on non-object JSON bodies.

    The bt-proof endpoint is called by the client-side JS challenge and
    is expected to be tolerant of any payload. A JSON array body (e.g.
    ['bad']) must be handled gracefully: respond 204 and record the
    caller's IP in the detective state, without raising a 500 from
    dict-style access on a list.
    """
    client, fake = _client(monkeypatch)

    resp = client.post("/api/bt-proof", json=["bad"])

    assert resp.status_code == 204
    assert fake.proofs == ["127.0.0.1"]


def test_bt_proof_accepts_falsy_non_object_json_without_crashing(monkeypatch):
    """Verify /api/bt-proof handles an empty array body gracefully.

    Edge case for the non-object check above: an empty array `[]` is
    falsy in Python but still not a dict. The endpoint must not crash
    on this case and must continue to record the IP in detective state
    so the challenge still progresses.
    """
    client, fake = _client(monkeypatch)

    resp = client.post("/api/bt-proof", json=[])

    assert resp.status_code == 204
    assert fake.proofs == ["127.0.0.1"]


def test_bt_proof_preserves_browser_flags(monkeypatch):
    """Verify /api/bt-proof stores the webdriver and plugins flags.

    The bt-proof payload carries short boolean flags (wd for
    webdriver_detected, pl for no_plugins). These must round-trip into
    the detective state unchanged so downstream scoring can use them
    to flag automated scrapers. This guards against an accidental
    type coercion (e.g. truthy 1 instead of True) silently flipping
    the bot detection signal.
    """
    client, fake = _client(monkeypatch)

    resp = client.post("/api/bt-proof", json={"wd": True, "pl": 0})

    assert resp.status_code == 204
    entry = fake._js_proof["127.0.0.1"]
    assert entry["webdriver_detected"] is True
    assert entry["no_plugins"] is True
