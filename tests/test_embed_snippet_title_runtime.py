"""Execute the browser-neutral embed-snippet naming regression (#2251)."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_embed_snippet_names_the_iframe_it_generates():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    result = subprocess.run(
        [node, str(Path(__file__).parent / "js" / "embed_snippet_title.test.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
