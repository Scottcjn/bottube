# SPDX-License-Identifier: MIT
from pathlib import Path


DISCOVER_TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "discover.html"


def test_agent_card_escapes_api_backed_profile_fields():
    html = DISCOVER_TEMPLATE.read_text(encoding="utf-8")

    assert "encodeURIComponent(agentName)" in html
    assert 'src="${escapeAttribute(avatarUrl)}"' in html
    assert 'alt="${escapeAttribute(displayName)}"' in html
    assert "${escapeHtml(displayName)}" in html
    assert "${escapeHtml(agent.bio || '')}" in html


def test_agent_card_has_attribute_and_url_helpers():
    html = DISCOVER_TEMPLATE.read_text(encoding="utf-8")

    assert "function escapeAttribute(value)" in html
    assert "function safeImageUrl(url)" in html
    assert "parsed.protocol === 'http:' || parsed.protocol === 'https:'" in html
    assert "value.startsWith('/') && !value.startsWith('//')" in html
