# SPDX-License-Identifier: MIT
"""Paid-path correctness for bottube_x402 (/api/premium/*).

Each test loads a private copy of bottube_x402 against a stub x402_config,
so nothing here leaks module state into other test files.

Two kinds of test:
  * Real SDK tests (skipped when the legacy ``x402`` package is absent) build
    an app with the paywall enabled and assert on the actual HTTP 402 body
    the SDK produces. A 0.01 USDC price must quote maxAmountRequired "10000".
  * Wiring tests replace PaymentMiddleware with a recorder and cover the
    fail-closed cases (testnet facilitator on mainnet, no treasury, bad price,
    unsupported network, SDK missing). Those never need the SDK.
"""

import base64
import importlib.util
import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest
from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TREASURY = "0x" + "ab" * 20
FACILITATOR = "https://facilitator.example.com"
API_KEY = "test-agent-key"

_load_counter = 0


def _stub_config(**overrides):
    cfg = types.ModuleType("x402_config")
    cfg.X402_NETWORK = "eip155:8453"
    cfg.USDC_BASE = BASE_USDC
    cfg.WRTC_BASE = "0x" + "cd" * 20  # present in the real config; must not leak
    cfg.FACILITATOR_URL = FACILITATOR
    cfg.BOTTUBE_TREASURY = TREASURY
    cfg.PRICE_VIDEO_STREAM_PREMIUM = "10000"   # 0.01 USDC in atomic units
    cfg.PRICE_API_BULK = "0"
    cfg.PRICE_PREMIUM_ANALYTICS = "10000"
    cfg.PRICE_PREMIUM_EXPORT = "5000"          # 0.005 USDC
    cfg.is_free = lambda p: p == "0" or p == ""
    cfg.has_cdp_credentials = lambda: False

    def _no_wallet():
        raise RuntimeError("not in tests")

    cfg.create_agentkit_wallet = _no_wallet
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _load_module(monkeypatch, cfg):
    """Import a fresh, uniquely named copy of bottube_x402 against cfg."""
    global _load_counter
    _load_counter += 1
    monkeypatch.setitem(sys.modules, "x402_config", cfg)
    monkeypatch.delenv("X402_FACILITATOR_URL", raising=False)
    name = "bottube_x402_under_test_%d" % _load_counter
    spec = importlib.util.spec_from_file_location(name, ROOT / "bottube_x402.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_db(tmp_path):
    db_path = tmp_path / "bottube.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE agents (id INTEGER PRIMARY KEY, agent_name TEXT, "
            "display_name TEXT, api_key TEXT, bio TEXT, is_human INTEGER DEFAULT 0)"
        )
        conn.execute(
            "INSERT INTO agents (agent_name, display_name, api_key, bio) VALUES (?, ?, ?, '')",
            ("tester", "Tester", API_KEY),
        )
    return str(db_path)


def _app(module, tmp_path):
    app = Flask("x402_paywall_test")
    app.config["TESTING"] = True
    module.init_app(app, _make_db(tmp_path))
    return app


class _RecordingMiddleware:
    """Stands in for x402.flask.middleware.PaymentMiddleware."""

    instances = []

    def __init__(self, app):
        self.app = app
        self.calls = []
        _RecordingMiddleware.instances.append(self)

    def add(self, **kwargs):
        self.calls.append(kwargs)


@pytest.fixture()
def recorder():
    _RecordingMiddleware.instances = []
    return _RecordingMiddleware


def _with_recorder(module, recorder):
    module.PaymentMiddleware = recorder
    module.X402_MIDDLEWARE = True
    return module


# ---------------------------------------------------------------------------
# Real SDK: the 402 body the client actually sees
# ---------------------------------------------------------------------------

def _sdk():
    return pytest.importorskip("x402.flask.middleware")


def test_real_sdk_quotes_atomic_amount_for_each_paid_route(monkeypatch, tmp_path):
    _sdk()
    module = _load_module(monkeypatch, _stub_config())
    assert module.X402_MIDDLEWARE is True
    client = _app(module, tmp_path).test_client()

    expected = {
        "/api/premium/videos": "10000",
        "/api/premium/analytics/tester": "10000",
        "/api/premium/trending/export": "5000",
    }
    for path, amount in expected.items():
        resp = client.get(path, headers={"Accept": "application/json"})
        assert resp.status_code == 402, (path, resp.status_code)
        body = resp.get_json()
        accepts = body["accepts"]
        assert len(accepts) == 1
        req = accepts[0]
        assert req["maxAmountRequired"] == amount, (path, req["maxAmountRequired"])
        assert req["network"] == "base"
        assert req["payTo"] == TREASURY
        assert req["asset"].lower() == BASE_USDC.lower()


def test_real_sdk_does_not_serve_paid_data_for_a_bogus_payment(monkeypatch, tmp_path):
    _sdk()
    module = _load_module(monkeypatch, _stub_config())
    client = _app(module, tmp_path).test_client()

    bogus = base64.b64encode(json.dumps({"x402Version": 1, "scheme": "exact"}).encode()).decode()
    resp = client.get("/api/premium/videos", headers={"X-PAYMENT": bogus, "Accept": "application/json"})
    assert resp.status_code == 402


def test_real_sdk_receives_the_configured_facilitator(monkeypatch, tmp_path):
    sdk_mw = _sdk()
    seen = []
    real_client = sdk_mw.FacilitatorClient

    def _spy(config=None):
        seen.append(config)
        return real_client(config)

    monkeypatch.setattr(sdk_mw, "FacilitatorClient", _spy)
    module = _load_module(monkeypatch, _stub_config())
    _app(module, tmp_path)

    # The SDK rebuilds every route's handler on each add(), so expect >= 3.
    assert len(seen) >= 3
    assert all(cfg is not None and cfg["url"] == FACILITATOR for cfg in seen)


# ---------------------------------------------------------------------------
# Wiring: price units, facilitator, network
# ---------------------------------------------------------------------------

def test_middleware_gets_usd_money_strings_and_facilitator(monkeypatch, tmp_path, recorder):
    module = _with_recorder(_load_module(monkeypatch, _stub_config()), recorder)
    _app(module, tmp_path)

    assert len(recorder.instances) == 1
    calls = {c["path"]: c for c in recorder.instances[0].calls}
    assert calls["/api/premium/videos"]["price"] == "$0.01"
    assert calls["/api/premium/analytics/*"]["price"] == "$0.01"
    assert calls["/api/premium/trending/export"]["price"] == "$0.005"
    for call in calls.values():
        assert call["network"] == "base"
        assert call["pay_to_address"] == TREASURY
        assert call["facilitator_config"] == {"url": FACILITATOR}


def test_facilitator_env_override_and_auth_hook(monkeypatch, tmp_path, recorder):
    def _headers():
        return {"verify": {}, "settle": {}}

    module = _load_module(monkeypatch, _stub_config(facilitator_create_headers=_headers))
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://mainnet-facilitator.example.org/")
    _with_recorder(module, recorder)
    _app(module, tmp_path)

    call = recorder.instances[0].calls[0]
    assert call["facilitator_config"]["url"] == "https://mainnet-facilitator.example.org"
    assert call["facilitator_config"]["create_headers"] is _headers


def test_testnet_facilitator_allowed_on_testnet(monkeypatch, tmp_path, recorder):
    cfg = _stub_config(X402_NETWORK="eip155:84532", FACILITATOR_URL="https://x402.org/facilitator")
    module = _with_recorder(_load_module(monkeypatch, cfg), recorder)
    _app(module, tmp_path)

    calls = recorder.instances[0].calls
    assert calls and all(c["network"] == "base-sepolia" for c in calls)


def test_atomic_to_usdc_conversion():
    spec = importlib.util.spec_from_file_location("bottube_x402_units", ROOT / "bottube_x402.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._atomic_to_usdc("10000") == "0.01"
    assert module._atomic_to_usdc("5000") == "0.005"
    assert module._atomic_to_usdc("1000000") == "1"
    assert module._atomic_to_usdc("1") == "0.000001"
    assert module._atomic_to_sdk_money("10000") == "$0.01"
    for bad in ("0.01", "$0.01", "-1", "1e4", "", "10 000"):
        with pytest.raises(ValueError):
            module._atomic_to_usdc(bad)


# ---------------------------------------------------------------------------
# Fail closed: never serve paid data free, never quote an unpayable price
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"FACILITATOR_URL": "https://x402.org/facilitator"}, "testnet_only_facilitator_on_mainnet"),
        ({"FACILITATOR_URL": "https://www.x402.org/facilitator"}, "testnet_only_facilitator_on_mainnet"),
        ({"FACILITATOR_URL": ""}, "no_facilitator_configured"),
        ({"FACILITATOR_URL": "http://facilitator.example.com"}, "facilitator_url_must_be_https"),
        ({"BOTTUBE_TREASURY": ""}, "treasury_not_configured"),
        ({"PRICE_VIDEO_STREAM_PREMIUM": "0.01"}, "invalid_price_config"),
        ({"X402_NETWORK": "eip155:1"}, "unsupported_network"),
    ],
)
def test_paid_routes_fail_closed(monkeypatch, tmp_path, recorder, overrides, reason):
    module = _with_recorder(_load_module(monkeypatch, _stub_config(**overrides)), recorder)
    client = _app(module, tmp_path).test_client()

    assert recorder.instances == []  # no paywall registered, so no quote
    for path in ("/api/premium/videos", "/api/premium/analytics/tester", "/api/premium/trending/export"):
        resp = client.get(path)
        assert resp.status_code == 503, (path, resp.status_code)
        assert resp.get_json() == {"error": "payment_unavailable", "reason": reason, "protocol": "x402"}

    info = client.get("/api/x402/info").get_json()
    assert info["pricing_mode"] == "unavailable"
    assert info["unavailable_reason"] == reason
    assert info["facilitator"] is None
    # Non-premium routes are untouched.
    assert client.get("/api/x402/payments").status_code == 200


def test_paid_routes_fail_closed_without_sdk(monkeypatch, tmp_path):
    module = _load_module(monkeypatch, _stub_config())
    module.X402_MIDDLEWARE = False
    client = _app(module, tmp_path).test_client()
    resp = client.get("/api/premium/videos")
    assert resp.status_code == 503
    assert resp.get_json()["reason"] == "x402_sdk_not_installed"


def test_only_paid_routes_are_blocked(monkeypatch, tmp_path, recorder):
    cfg = _stub_config(FACILITATOR_URL="", PRICE_PREMIUM_ANALYTICS="0", PRICE_PREMIUM_EXPORT="0")
    module = _with_recorder(_load_module(monkeypatch, cfg), recorder)
    client = _app(module, tmp_path).test_client()
    assert client.get("/api/premium/videos").status_code == 503
    # Free route passes the guard and reaches the view (404: agent unknown).
    assert client.get("/api/premium/analytics/nobody").status_code == 404


# ---------------------------------------------------------------------------
# /api/x402/info and wallet responses
# ---------------------------------------------------------------------------

def test_info_reports_consistent_paid_config(monkeypatch, tmp_path, recorder):
    module = _with_recorder(_load_module(monkeypatch, _stub_config()), recorder)
    client = _app(module, tmp_path).test_client()
    resp = client.get("/api/x402/info")
    assert resp.status_code == 200
    info = resp.get_json()

    assert info["pricing_mode"] == "paid"
    assert info["network"] == "eip155:8453"
    assert info["network_name"] == "base"
    assert info["facilitator"] == FACILITATOR
    assert info["treasury"] == TREASURY
    prices = {ep["path"]: (ep["price_usdc"], ep["price_atomic"]) for ep in info["premium_endpoints"]}
    assert prices == {
        "/api/premium/videos": ("0.01", "10000"),
        "/api/premium/analytics/<agent>": ("0.01", "10000"),
        "/api/premium/trending/export": ("0.005", "5000"),
    }
    raw = resp.get_data(as_text=True).lower()
    assert "wrtc" not in raw
    assert "reference_rate" not in raw


def test_wallet_accepts_x_api_key_and_hides_wrtc(monkeypatch, tmp_path, recorder):
    module = _with_recorder(_load_module(monkeypatch, _stub_config()), recorder)
    client = _app(module, tmp_path).test_client()

    for headers in ({"X-API-Key": API_KEY}, {"Authorization": "Bearer " + API_KEY}):
        resp = client.get("/api/agents/me/coinbase-wallet", headers=headers)
        assert resp.status_code == 200, headers
        body = resp.get_json()
        assert body["agent"] == "tester"
        assert "wrtc" not in resp.get_data(as_text=True).lower()

    assert client.get("/api/agents/me/coinbase-wallet").status_code == 401
    resp = client.post(
        "/api/agents/me/coinbase-wallet",
        headers={"X-API-Key": API_KEY},
        json={"coinbase_address": "0x" + "12" * 20},
    )
    assert resp.status_code == 200
    assert resp.get_json()["method"] == "manual_link"
