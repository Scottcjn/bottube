"""Execute the browser-neutral RTC tip preset regression."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_tip_controls_bind_preset_and_custom_input_state():
    template = Path("bottube_templates/watch.html").read_text(encoding="utf-8")
    assert template.count('class="tip-amount-btn" type="button"') == 5
    assert template.count('aria-pressed="false" onclick="selectTipAmount') == 5
    assert 'id="tip-amount"' in template
    assert 'oninput="clearTipPresetSelection()"' in template


def test_custom_tip_clears_stale_preset_state():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    result = subprocess.run(
        [node, str(Path(__file__).parent / "js" / "tip_preset_state.test.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
