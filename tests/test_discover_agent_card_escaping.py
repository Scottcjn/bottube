# SPDX-License-Identifier: MIT
from pathlib import Path


DISCOVER_TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "discover.html"


def test_agent_card_escapes_api_backed_profile_fields():
    """Verify agent card template escapes user-controlled profile fields.

    The agent card is rendered with values pulled from the agents API
    (agentName, avatarUrl, displayName, bio). All of those must be run
    through escape helpers before being inserted into HTML/attributes/URLs
    so a malicious agent profile cannot inject script tags, break out of
    `src="..."`, or steal clicks via attribute injection.
    """
    html = DISCOVER_TEMPLATE.read_text(encoding="utf-8")

    assert "encodeURIComponent(agentName)" in html
    assert 'src="${escapeAttribute(avatarUrl)}"' in html
    assert 'alt="${escapeAttribute(displayName)}"' in html
    assert "${escapeHtml(displayName)}" in html
    assert "${escapeHtml(agent.bio || '')}" in html


def test_agent_card_has_attribute_and_url_helpers():
    """Verify the discover template defines the escape + URL helper functions.

    The previous test asserts the helpers are *called* on user-controlled
    values; this one asserts the helpers are *defined* in the template
    and that safeImageUrl only accepts http(s) and same-origin relative
    URLs (rejects javascript:, data:, and protocol-relative //evil.com).
    Without these helpers in scope the assertions above would silently
    become no-ops after a template refactor.
    """
    html = DISCOVER_TEMPLATE.read_text(encoding="utf-8")

    assert "function escapeAttribute(value)" in html
    assert "function safeImageUrl(url)" in html
    assert "parsed.protocol === 'http:' || parsed.protocol === 'https:'" in html
    assert "value.startsWith('/') && !value.startsWith('//')" in html


def test_tag_chips_do_not_embed_names_in_inline_javascript():
    """Verify tag chips do not use inline onclick with raw tag names.

    Tag chips on the discover page are clickable and search by tag. The
    old implementation put the tag name into an inline onclick handler,
    which would let a tag with a quote break out of the handler and run
    arbitrary JS. The current implementation stores the tag on a data-*
    attribute and delegates clicks via addEventListener. This test
    prevents the old unsafe pattern from being reintroduced.
    """
    html = DISCOVER_TEMPLATE.read_text(encoding="utf-8")

    assert 'data-tag="${escapeAttribute(tag.name)}"' in html
    assert "onclick=\"searchByTag('${escapeHtml(tag.name)}')\"" not in html
    assert "document.getElementById('tagsCloud').addEventListener('click'" in html
    assert "target.dataset.tag" in html
