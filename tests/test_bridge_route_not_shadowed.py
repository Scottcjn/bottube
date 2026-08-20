# SPDX-License-Identifier: MIT
"""Regression test: /bridge must be served by the wRTC blueprint, not a stub.

`bottube_server.py` used to declare its own `@app.route("/bridge")` returning
`bridge.html` with hardcoded placeholders (balance 0.0, reserve wallet
"Not connected — log in to view", no `wrtc_mint` at all). Because that
module-level decorator runs on import — thousands of lines before
`app.register_blueprint(wrtc_bp)` — it won the URL match, and
`wrtc_bridge_blueprint.wrtc_bridge_landing()`, the handler that actually
passes the mint, the reserve wallet and the logged-in user's balance, was
unreachable.

The visible damage: `bridge.html` interpolates `wrtc_mint` five times, so the
contract address rendered blank, the Copy button copied an empty string, and
the Solscan / Birdeye / GeckoTerminal links degraded to bare
`https://solscan.io/token/` URLs.
"""

import pytest

import wrtc_bridge_blueprint


def _bridge_endpoints(app):
    return sorted(
        r.endpoint for r in app.url_map.iter_rules() if str(r) == "/bridge"
    )


def test_bridge_is_served_only_by_the_wrtc_blueprint(app):
    assert _bridge_endpoints(app) == ["wrtc_bridge.wrtc_bridge_landing"]


def test_bridge_page_renders_the_contract_address_block(client):
    """The copy-to-clipboard contract address must not be empty.

    Note the mint also appears once as a hardcoded Raydium swap link, so a
    bare `WRTC_MINT in html` check passes even with the stub -- assert on the
    interpolated block instead.
    """
    response = client.get("/bridge")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert f'class="addr">{wrtc_bridge_blueprint.WRTC_MINT}</span>' in html
    assert 'class="addr"></span>' not in html
    assert "copyText('', this)" not in html


def test_bridge_explorer_links_are_not_truncated(client):
    """A blank wrtc_mint silently produced links pointing at nothing."""
    html = client.get("/bridge").get_data(as_text=True)

    for broken in (
        'href="https://solscan.io/token/"',
        'href="https://birdeye.so/token/?chain=solana"',
        'href="https://www.geckoterminal.com/solana/tokens/"',
    ):
        assert broken not in html, f"explorer link rendered without a mint: {broken}"
