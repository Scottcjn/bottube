"""Execute the browser-neutral badge clipboard regression."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_repeated_badge_copy_excludes_transient_button_label():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    result = subprocess.run(
        [node, str(Path(__file__).parent / "js" / "badges_copy_code.test.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
