"""Accessibility checks for the create-collaboration type picker.

Bounty: Scottcjn/rustchain-bounties#1618
Issue: Scottcjn/bottube#1321
"""
from __future__ import annotations

import re
from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "collaboration_new.html"


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _option_tag(html: str, collab_type: str) -> str:
    match = re.search(
        rf'<div class="collab-type-option[^>]*data-type="{re.escape(collab_type)}"[^>]*>',
        html,
    )
    assert match, f"missing collaboration option for {collab_type}"
    return match.group(0)


def test_collaboration_type_picker_is_named_radio_group() -> None:
    html = _template()

    assert 'role="radiogroup"' in html
    assert 'aria-label="Collaboration type"' in html


def test_each_collaboration_type_option_is_keyboard_focusable_radio() -> None:
    html = _template()

    for collab_type in ("duet", "co-upload", "remix"):
        option = _option_tag(html, collab_type)
        assert 'role="radio"' in option
        assert 'tabindex="0"' in option
        assert f"handleTypeKeydown(event, '{collab_type}')" in option


def test_collaboration_type_selection_keeps_aria_checked_in_sync() -> None:
    html = _template()

    assert 'aria-checked="true"' in _option_tag(html, "duet")
    assert 'aria-checked="false"' in _option_tag(html, "co-upload")
    assert 'aria-checked="false"' in _option_tag(html, "remix")
    assert "opt.setAttribute('aria-checked', isSelected ? 'true' : 'false')" in html
    assert "event.key === 'Enter' || event.key === ' '" in html
