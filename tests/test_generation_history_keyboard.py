"""Regression coverage for issue #2004 generation-history semantics."""

from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "bottube_templates"
    / "generate.html"
).read_text(encoding="utf-8")


def test_completed_history_rows_are_native_safe_links():
    assert "if (j.status === 'completed')" in TEMPLATE
    assert '<a class="gen-history-item"' in TEMPLATE
    assert 'href="${P}/api/gemini/job/${encodeURIComponent(j.job_id)}"' in TEMPLATE
    assert 'target="_blank" rel="noopener noreferrer"' in TEMPLATE
    assert 'aria-label="Open completed generation: ${escHtml(j.prompt)}"' in TEMPLATE


def test_incomplete_history_rows_are_truthful_non_actions():
    assert 'return `<div class="gen-history-item">${content}</div>`;' in TEMPLATE
    assert '<div class="gen-history-item" onclick=' not in TEMPLATE
    assert 'onkeydown=' not in TEMPLATE
    assert 'onkeyup=' not in TEMPLATE


def test_completed_history_links_have_visible_focus():
    assert 'a.gen-history-item:focus-visible' in TEMPLATE
    assert 'outline: 3px solid var(--accent);' in TEMPLATE
