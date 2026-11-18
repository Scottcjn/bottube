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


# --- Homepage copy left behind by wording removals --------------------------
# Cutting a phrase out of a sentence once left the hero reading "generate your
# own ." and left a payments FAQ answer that no longer matched its FAQPage
# JSON-LD. These checks render the homepage and read it the way a visitor and
# a search engine do.

import json
import re
from html import unescape
from html.parser import HTMLParser


class _HomeParser(HTMLParser):
    """Collects the hero sub-line, visible payments FAQ pairs and JSON-LD blocks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hero_sub = None
        self.faq = []  # [(question, answer)]
        self.jsonld = []
        self._stack = []  # what we are currently capturing
        self._buf = []
        self._in_pay_faq = 0
        self._question = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if tag == "section" and "pay-faq" in classes:
            self._in_pay_faq += 1
        elif self._in_pay_faq and tag == "section":
            self._in_pay_faq += 1
        capture = None
        if tag == "div" and "hero-sub" in classes and self.hero_sub is None:
            capture = "hero"
        elif tag == "script" and attrs.get("type") == "application/ld+json":
            capture = "jsonld"
        elif self._in_pay_faq and tag == "summary":
            capture = "question"
        elif self._in_pay_faq and tag == "p" and self._question is not None:
            capture = "answer"
        if capture:
            self._stack.append((tag, capture))
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "section" and self._in_pay_faq:
            self._in_pay_faq -= 1
        if not self._stack or self._stack[-1][0] != tag:
            return
        _, capture = self._stack.pop()
        text = "".join(self._buf)
        if capture == "jsonld":
            self.jsonld.append(text)
            return
        text = re.sub(r"\s+", " ", text).strip()
        if capture == "hero":
            self.hero_sub = text
        elif capture == "question":
            self._question = text
        elif capture == "answer":
            self.faq.append((self._question, text))
            self._question = None

    def handle_data(self, data):
        if self._stack:
            self._buf.append(data)


def _parse_home(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    parser = _HomeParser()
    parser.feed(html)
    return html, parser


def _faq_answers_from_jsonld(blocks):
    """Map question -> set of answer texts across every FAQPage block."""
    answers = {}
    for raw in blocks:
        data = json.loads(raw)
        for node in data if isinstance(data, list) else [data]:
            if node.get("@type") != "FAQPage":
                continue
            for entry in node.get("mainEntity", []):
                text = re.sub(r"\s+", " ", unescape(entry["acceptedAnswer"]["text"])).strip()
                answers.setdefault(entry["name"].strip(), set()).add(text)
    return answers


# A sentence must not end on a word that needs something after it.
_DANGLING_TAIL = re.compile(
    r"\b(or|and|with|via|your own|of|to|for|the|a|an|by|on)\s*[.!?]$", re.IGNORECASE
)


def test_home_hero_sub_is_complete_sentences(client):
    html, home = _parse_home(client)
    hero = home.hero_sub
    assert hero, "homepage has no .hero-sub line"
    # Punctuation glued to a space is the mark of a phrase cut out of a sentence.
    assert not re.search(r"\s[.,;:!?]", hero), f"hero has a dangling fragment: {hero!r}"
    assert "  " not in hero and hero.endswith((".", "!", "?")), hero
    for sentence in re.split(r"(?<=[.!?])\s+", hero):
        assert len(sentence.split()) >= 3, f"hero sentence too short to be whole: {sentence!r}"
        assert not _DANGLING_TAIL.search(sentence), f"hero sentence ends mid-thought: {sentence!r}"
    _assert_clean(html, "/")


def test_home_payments_faq_matches_its_jsonld(client):
    _, home = _parse_home(client)
    assert home.faq, "homepage renders no payments FAQ entries"
    answers = _faq_answers_from_jsonld(home.jsonld)
    for question, visible in home.faq:
        assert question in answers, f"visible FAQ question has no FAQPage JSON-LD entry: {question!r}"
        assert answers[question] == {visible}, (
            f"FAQ {question!r}: visible answer and JSON-LD answer differ\n"
            f"  visible: {visible!r}\n  json-ld: {sorted(answers[question])!r}"
        )
        assert not re.search(r"\s[.,;:!?]", visible), f"dangling fragment in FAQ answer: {visible!r}"


def test_payments_faq_names_a_working_payment_method():
    from seo_routes import PAYMENT_FAQ

    question, answer = next((q, a) for q, a in PAYMENT_FAQ if "cryptocurrenc" in q.lower())
    lowered = answer.lower()
    # The answer must say how to pay today, not just that something exists.
    assert "card" in lowered and "credits page" in lowered
    # The crypto checkout gateway is not configured; no coin may read as accepted.
    assert "coming soon" in lowered
    for needle in FORBIDDEN + ("exchange", "trade", "trading", "dex", "swap"):
        assert not re.search(r"\b" + re.escape(needle) + r"\b", lowered), needle
