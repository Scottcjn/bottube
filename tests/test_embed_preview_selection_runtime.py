"""Execute the browser-neutral embed-preview selection regression."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_embed_preview_exposes_exactly_one_selected_video():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    result = subprocess.run(
        [node, str(Path(__file__).parent / "js" / "embed_preview_selection.test.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
