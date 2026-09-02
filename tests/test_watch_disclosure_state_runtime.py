"""Static and executable regressions for watch-page disclosure controls."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_watch_disclosure_controls_name_their_panels():
    template = Path("bottube_templates/watch.html").read_text(encoding="utf-8")
    relationships = {
        "share-btn": "share-panel",
        "embed-toggle-btn": "embed-panel",
        "save-btn": "save-panel",
        "tip-toggle-btn": "tip-panel",
    }
    for control, panel in relationships.items():
        marker = f'id="{control}"'
        line = next(line for line in template.splitlines() if marker in line)
        assert f'aria-controls="{panel}"' in line
        assert 'aria-expanded="false"' in line


def test_watch_disclosures_synchronize_every_transition():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    result = subprocess.run(
        [node, str(Path(__file__).parent / "js" / "watch_disclosure_state.test.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
