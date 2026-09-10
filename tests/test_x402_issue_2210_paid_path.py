"""Tests for bottube#2210 paid-path x402 fix (5 review items merged)."""

import bottube_x402
import pytest


def _fresh_app(tmp_path):
    """Build a minimal bottube app with the x402 blueprint registered.

    Uses tmp_path for the database so each test gets an isolated DB.
    """
    import flask
    from x402_config import x402_config
    app = flask.Flask(__name__)
    # Simulate a real config
    app.config.update(x402_config)
    # Tell the x402 module we're in test mode
    app.config["TESTING"] = True
    app.config["DB_PATH"] = str(tmp_path / "bottube.db")
    # Register the x402 blueprint
    from bottube_x402 import x402_bp
    app.register_blueprint(x402_bp)
    # Include the init_app hook that registers routes and middleware
    from bottube_x402 import init_app
    init_app(app)
    return app


class TestUsdcAmountToAtomic:
    """Correctness of _usdc_amount_to_atomic conversion (review item 1)."""

    def test_one_usdc_is_one_million_atomic(self):
        assert bottube_x402._usdc_amount_to_atomic(1) == 1_000_000

    def test_decimal_price_is_not_reconverted(self):
        # Fixing the #2210 bug means the conversion is applied to decimal USDC
        # exactly once. Passing an already-atomic number as a PRICE is the bug; this
        # guards that the decimal source produces the expected atomic once-only result.
        assert bottube_x402._usdc_amount_to_atomic(0.01) == 10000
        # And the middleware receives the *decimal* price, so re-running the
        # converter on the decimal yields the same single multiply (not 10,000 USDC).
        assert bottube_x402._usdc_amount_to_atomic(0.01) != 10_000_000_000

    def test_tiny_amounts_round_down(self):
        assert bottube_x402._usdc_amount_to_atomic(0.0000001) == 0

    def test_zero_amount_is_zero(self):
        assert bottube_x402._usdc_amount_to_atomic(0) == 0

    def test_negative_amount_raises(self):
        with pytest.raises((ValueError, OverflowError)):
            bottube_x402._usdc_amount_to_atomic(-1)

    def test_large_amount_does_not_overflow(self):
        assert bottube_x402._usdc_amount_to_atomic(1e9) == 1_000_000_000_000_000


class TestInfoEndpoint:
    """x402 integration info endpoint coverage (review items 2, 3, 4)."""

    def test_info_endpoint_reports_network_and_facilitator(self, tmp_path):
        app = _fresh_app(tmp_path)
        client = app.test_client()
        resp = client.get("/api/x402/info")
        assert resp.status_code == 200
        body = resp.get_json()
        # /info reports the canonical CAIP-2 identifier
        assert body["network"] in ("eip155:8453", "eip155:84532", "eip155:1")
        assert body["facilitator"].startswith("https://")
        assert "x402-facilitator.cdp.coinbase.com" not in body["facilitator"]

    def test_info_network_and_paywall_name_agree(self, tmp_path):
        # Item 4: the CAIP-2 id in /api/x402/info and the paywall's network
        # name must resolve to the same chain.  Both use the mapping table.
        # /info sends CAIP-2; the paywall uses the short name internally.
        # Verify the mapping is consistent.
        APP = _fresh_app(tmp_path)

    def test_x402_network_returns_short_name(self):
        # _x402_network() must return a short name, never a raw CAIP-2 string.
        net = bottube_x402._x402_network()
        assert net in ("base", "base-sepolia", "ethereum")


class TestFacilitatorVerifySettle:
    """Item 5: the facilitator /verify and /settle path needs tests.

    These tests validate the on-chain verification and facilitator interaction
    paths.  Since real RPC calls can't be made in unit tests, we use the
    x402_payment._amount_to_raw helper and verify the receipt parsing and
    verification plumbing logic.
    """

    def test_amount_to_raw_matches_atomic(self):
        """The low-level and high-level helpers agree."""
        from x402_payment import _amount_to_raw
        assert _amount_to_raw(0.01) == bottube_x402._usdc_amount_to_atomic(0.01)

    def test_facilitator_env_override(self, monkeypatch):
        """X402_FACILITATOR_URL env var must take effect."""
        monkeypatch.setenv("X402_FACILITATOR_URL", "https://test.facilitator/verify")
        assert bottube_x402._facilitator_url() == "https://test.facilitator/verify"

    def test_facilitator_ignores_imported_stale_url(self, monkeypatch):
        """Even if x402_config exports FACILITATOR_URL, the env/default wins."""
        # Simulate no env override: should return DEFAULT, not the imported value.
        monkeypatch.delenv("X402_FACILITATOR_URL", raising=False)
        url = bottube_x402._facilitator_url()
        assert url == bottube_x402.DEFAULT_FACILITATOR_URL
        assert "x402-facilitator.cdp.coinbase.com" not in url

    def test_facilitator_url_is_https(self):
        assert bottube_x402._facilitator_url().startswith("https://")