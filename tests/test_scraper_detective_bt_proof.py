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
    client, fake = _client(monkeypatch)

    resp = client.post("/api/bt-proof", json=["bad"])

    assert resp.status_code == 204
    assert fake.proofs == ["127.0.0.1"]


def test_bt_proof_accepts_falsy_non_object_json_without_crashing(monkeypatch):
    client, fake = _client(monkeypatch)

    resp = client.post("/api/bt-proof", json=[])

    assert resp.status_code == 204
    assert fake.proofs == ["127.0.0.1"]


def test_bt_proof_preserves_browser_flags(monkeypatch):
    client, fake = _client(monkeypatch)

    resp = client.post("/api/bt-proof", json={"wd": True, "pl": 0})

    assert resp.status_code == 204
    entry = fake._js_proof["127.0.0.1"]
    assert entry["webdriver_detected"] is True
    assert entry["no_plugins"] is True
