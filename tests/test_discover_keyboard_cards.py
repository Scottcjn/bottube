"""Regression coverage for issue #2002 Discover keyboard navigation."""

from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "bottube_templates"
    / "discover.html"
).read_text(encoding="utf-8")


def test_discover_navigation_cards_use_native_links():
    """Creator and video navigation must work with native Enter activation."""
    assert '<a class="agent-card" href="/agent/${encodeURIComponent(agentName)}"' in TEMPLATE
    assert '<a class="video-card" href="/watch/${encodeURIComponent(video.id)}"' in TEMPLATE
    assert 'aria-label="View creator ${escapeAttribute(displayName)}"' in TEMPLATE
    assert 'aria-label="Watch ${escapeAttribute(video.title || \'video\')}"' in TEMPLATE

    assert '<div class="agent-card" onclick=' not in TEMPLATE
    assert '<div class="video-card" onclick="window.location=' not in TEMPLATE


def test_discover_category_cards_use_native_buttons_once():
    """Native buttons provide Enter/Space without a duplicate key handler."""
    assert '<button type="button" class="video-card category-card"' in TEMPLATE
    assert 'onclick="searchByCategory(\'${cat.id}\')"' in TEMPLATE
    assert 'aria-label="Browse ${escapeAttribute(cat.name)} videos"' in TEMPLATE
    assert 'onkeydown=' not in TEMPLATE
    assert 'onkeyup=' not in TEMPLATE


def test_discover_interactive_cards_have_visible_focus():
    assert '.video-card:focus-visible' in TEMPLATE
    assert '.agent-card:focus-visible' in TEMPLATE
    assert 'outline: 3px solid var(--accent);' in TEMPLATE
