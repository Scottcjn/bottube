# SPDX-License-Identifier: MIT
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_base_template_reserves_logo_width_on_mobile():
    template = (ROOT / 'bottube_templates' / 'base.html').read_text(encoding='utf-8')

    assert 'flex: 0 0 auto;' in template
    assert 'display: inline-flex;' in template
    assert '.search-bar {' in template and 'margin-left: auto;' in template
    assert 'flex: 1 1 0;' in template
    assert '.mobile-menu-btn { display: block; flex: 0 0 auto; }' in template


def test_base_template_trims_mobile_search_button_padding():
    template = (ROOT / 'bottube_templates' / 'base.html').read_text(encoding='utf-8')

    assert '.search-bar button { padding: 8px 12px; }' in template
    assert 'font-size: 13px;' in template
