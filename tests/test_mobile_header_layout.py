# SPDX-License-Identifier: MIT
"""Regression tests for mobile header layout and logo/search non-overlap.

Fixes #1713: Mobile header search form overlaps 'Tube' portion of logo at 390px.
"""

from __future__ import annotations
import re
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parents[1]


def test_base_html_templates_contain_mobile_header_overlap_guards() -> None:
    """Verify that both base.html and bottube_templates/base.html protect logo and search layout."""
    templates = [
        ROOT / "base.html",
        ROOT / "bottube_templates" / "base.html",
    ]

    for tpl_path in templates:
        content: str = tpl_path.read_text(encoding="utf-8")

        # 1. Base header-left and logo must not shrink or wrap
        assert ".header-left" in content
        assert "flex-shrink: 0;" in content
        assert "white-space: nowrap;" in content

        # 2. At max-width: 480px, header has gap, header-left has flex-shrink: 0 and search-bar is bounded
        assert re.search(
            r"@media\s*\(\s*max-width:\s*480px\s*\).*?\.header-left\s*\{[^}]*flex-shrink:\s*0;",
            content,
            re.DOTALL,
        )
        assert re.search(
            r"@media\s*\(\s*max-width:\s*480px\s*\).*?\.search-bar\s*\{[^}]*min-width:\s*0;",
            content,
            re.DOTALL,
        )
