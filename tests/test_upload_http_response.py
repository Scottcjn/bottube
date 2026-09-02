"""Executable regression for logged-out upload response handling."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_upload_preserves_json_and_non_json_http_error_truth():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    result = subprocess.run(
        [node, str(Path(__file__).parent / "upload_http_response.test.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
