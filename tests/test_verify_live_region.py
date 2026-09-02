"""Static and executable regressions for provenance-verification feedback."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_verification_steps_and_verdict_expose_live_semantics():
    template = Path("bottube_templates/verify.html").read_text(encoding="utf-8")
    assert (
        'id="vrf-steps" role="log" aria-live="polite" '
        'aria-relevant="additions text"'
    ) in template
    assert (
        'id="vrf-verdict" role="status" aria-live="polite" '
        'aria-atomic="true"'
    ) in template
    assert "stepsEl.appendChild(row);" in template
    assert "verdEl.textContent = pass ? 'PASS' : 'FAIL';" in template


def test_invalid_verification_updates_log_and_verdict_runtime():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript runtime regression")

    result = subprocess.run(
        [node, str(Path(__file__).parent / "verify_live_region.test.cjs")],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
