# SPDX-License-Identifier: MIT
"""Official BoTTube surfaces stay silent on exchanges.

RTC on BoTTube is a prepaid service credit: it is topped up at /credits and
spent on the platform. Pages, shipped JS and token metadata must not link to,
name, or track clicks towards any exchange/DEX, must not print the wRTC
mint as a "buy this" hint, and must not offer a token listing or ask anyone
to provide liquidity.
"""

import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Lower-case needles. "12tadkxx" is the head of the Solana wRTC mint.
FORBIDDEN = (
    "raydium", "uniswap", "birdeye", "geckoterminal", "buy wrtc", "/otc",
    # No listing tier and no liquidity requirement is offered or asked for.
    "liquidity", "token listing",
)
MINT_HEAD = "12tadkxx"

SHIPPED_DIRS = ("bottube_templates", "bottube_static", "static")
SHIPPED_SUFFIXES = {".html", ".js", ".json", ".css", ".txt"}
# Vendored third-party bundle; not our copy.
SKIP_PARTS = {"swaggerui"}
# The bridge templates interpolate the mint from the blueprint; they never
# hardcode it, so the mint check applies to every shipped file too.


def _shipped_files():
    for dirname in SHIPPED_DIRS:
        base = ROOT / dirname
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if (
                path.is_file()
                and path.suffix in SHIPPED_SUFFIXES
                and not SKIP_PARTS.intersection(path.parts)
            ):
                yield path


def test_shipped_files_name_no_exchange():
    offenders = []
    for path in _shipped_files():
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for needle in FORBIDDEN + (MINT_HEAD,):
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)}: {needle!r}")
    assert not offenders, "exchange wording in shipped files:\n  " + "\n  ".join(offenders)


def test_beacon_atlas_get_listed_panel_has_no_token_tier():
    source = (ROOT / "bottube_static" / "beacon_atlas" / "advertise.js").read_text(encoding="utf-8")
    assert source.count("    id: '") == 1
    assert "id: 'agent'" in source
    assert "id: 'crypto'" not in source
    assert "list your token" not in source.lower()
    # The card template reads tier.fee; the old field name must not come back.
    assert "tier.fee" in source and "fee: '" in source
    assert "minLiquidity" not in source


def test_services_gateway_points_at_credits_not_otc():
    source = (ROOT / "rtc_services.py").read_text(encoding="utf-8").lower()
    assert "/otc" not in source
    assert "buy directly from miners" not in source
    assert MINT_HEAD not in source
    assert "/credits" in source


def test_bridge_modules_carry_no_swap_links():
    for name in ("wrtc_bridge.py", "wrtc_bridge_blueprint.py", "base_wrtc_bridge_blueprint.py"):
        source = (ROOT / name).read_text(encoding="utf-8").lower()
        for needle in ("raydium", "uniswap"):
            assert needle not in source, f"{name} still links {needle}"


def _insert_agent(app, name="doctrine_viewer", rtc_balance=0.0):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url,
                 created_at, last_active, rtc_balance)
            VALUES (?, ?, ?, '', '', '', ?, ?, ?)
            """,
            (name, name.title(), f"bottube_sk_{name}", time.time(), time.time(), rtc_balance),
        )
        db.execute(
            """
            INSERT INTO videos (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            ("doctrine001", cur.lastrowid, "Doctrine check", "doctrine001.mp4", time.time()),
        )
        db.commit()
        return int(cur.lastrowid)


def _assert_clean(html, page):
    lowered = html.lower()
    for needle in FORBIDDEN + (MINT_HEAD,):
        assert needle not in lowered, f"{page} renders {needle!r}"


@pytest.mark.parametrize("path", ["/upload", "/embed-guide", "/services"])
def test_public_pages_render_no_exchange_wording(client, path):
    response = client.get(path)
    assert response.status_code == 200
    _assert_clean(response.get_data(as_text=True), path)


def test_logged_in_watch_and_dashboard_render_no_exchange_wording(app, client):
    # A balance under 10 RTC is what makes the dashboard show its top-up box.
    agent_id = _insert_agent(app, rtc_balance=1.0)
    with client.session_transaction() as sess:
        sess["user_id"] = agent_id

    watch = client.get("/watch/doctrine001")
    assert watch.status_code == 200
    watch_html = watch.get_data(as_text=True)
    _assert_clean(watch_html, "/watch")
    assert "/credits" in watch_html

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    dashboard_html = dashboard.get_data(as_text=True)
    _assert_clean(dashboard_html, "/dashboard")
    assert "Need more credits for tipping?" in dashboard_html
