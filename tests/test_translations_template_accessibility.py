# SPDX-License-Identifier: MIT
from pathlib import Path


def _template() -> str:
    template = Path(__file__).resolve().parents[1] / "templates" / "translations.html"
    return template.read_text(encoding="utf-8")


def test_translation_search_has_persistent_accessible_label():
    html = _template()

    assert 'id="searchInput" aria-label="Search translations"' in html


def test_translation_video_links_isolate_new_tab_context():
    html = _template()

    assert 'target="_blank" rel="noopener noreferrer"' in html
