"""Execute the browser-neutral giveaway countdown timer regression."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_giveaway_countdown_uses_one_bounded_timer():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    test_file = Path(__file__).parent / "js" / "giveaway_countdown.test.cjs"
    result = subprocess.run(
        [node, str(test_file)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
