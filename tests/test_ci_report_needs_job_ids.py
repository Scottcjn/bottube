"""Exercise the outcome-report shell script with GitHub needs results."""
import re
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


@pytest.mark.parametrize("drift_result, expected_code, message", [
    ("success", 0, "All CI jobs completed successfully."),
    ("failure", 1, "A CI job FAILED"),
    ("cancelled", 1, "A CI job was CANCELLED"),
])
def test_report_includes_deployment_drift(drift_result, expected_code, message):
    report = yaml.safe_load(WORKFLOW.read_text())["jobs"]["report"]
    results = {job: "success" for job in report["needs"]}
    results["deployment-drift"] = drift_result
    script = report["steps"][0]["run"]
    # GitHub resolves missing context properties to the empty string.
    script = re.sub(r"\$\{\{\s*needs\.([\w-]+)\.result\s*\}\}",
                    lambda match: results.get(match[1], ""), script)
    completed = subprocess.run(["bash", "-e", "-c", script],
                               capture_output=True, text=True, timeout=5)
    assert completed.returncode == expected_code, completed.stdout
    assert message in completed.stdout
