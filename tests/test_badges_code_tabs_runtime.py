"""Contract and runtime regressions for badge code-format tabs."""

from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess

import pytest


class _TabContractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tabs = []
        self.panels = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("role") == "tab":
            self.tabs.append(attributes)
        elif attributes.get("role") == "tabpanel":
            self.panels[attributes["id"]] = attributes


def test_badge_code_tabs_have_unique_bidirectional_relationships():
    template = Path("bottube_templates/badges.html").read_text(encoding="utf-8")
    parser = _TabContractParser()
    parser.feed(template)

    assert len(parser.tabs) == 14
    assert len(parser.panels) == 14
    assert len({tab["id"] for tab in parser.tabs}) == len(parser.tabs)
    for tab in parser.tabs:
        panel = parser.panels[tab["aria-controls"]]
        assert panel["aria-labelledby"] == tab["id"]
        assert tab["aria-selected"] in {"true", "false"}


def test_badge_code_tab_runtime_synchronizes_selection_and_keyboard():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    result = subprocess.run(
        [node, str(Path(__file__).parent / "js" / "badges_code_tabs.test.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
