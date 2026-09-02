"""Static and executable regressions for public report outcomes."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_report_result_is_a_persistent_atomic_live_status():
    template = Path("bottube_templates/report.html").read_text(encoding="utf-8")
    assert (
        'id="r-toast" class="toast" role="status" '
        'aria-live="polite" aria-atomic="true"'
    ) in template


def test_report_result_announces_success_and_failure_paths():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    result = subprocess.run(
        [node, str(Path(__file__).parent / "report_status_live_region.test.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
